"""Orquestador del Monitor de Ninfas.

Coordina una fuente de video, YOLO/BoT-SORT, Supervision, identidad por color,
máquinas de estado por track, audio, salud y persistencia asíncrona.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(*_args, **_kwargs):
        return False


from ultralytics import YOLO

from modulos.audio_analysis import AudioMonitor, AudioMonitorNulo
from modulos.camara import CamaraStream
from modulos.comportamiento import (
    EstadoComportamiento,
    EventoComportamiento,
    GestorComportamiento,
    ObservacionComportamiento,
    TipoEvento,
)
from modulos.estado_monitor import EstabilizadorAnimo, SnapshotPeriodico
from modulos.fuente_video import describir_fuente, es_rtsp, resolver_fuente
from modulos.health_monitor import HealthMonitor
from modulos.identificador import IdentificadorColor
from modulos.movement_analysis import MovementMonitor
from modulos.recomendaciones import generar_recomendaciones
from modulos.vision_supervision import (
    GestorZonas,
    ProcesadorDetecciones,
    ResultadoVision,
    VisualizadorDetecciones,
)

RAIZ = Path(__file__).resolve().parent
load_dotenv(RAIZ / ".env")

MODELO_RUTA = RAIZ / "best.pt"
TRACKER_CONFIG = "botsort.yaml"

AVES_PREDETERMINADAS = [
    {"id": None, "nombre": "Yukki", "color": "amarilla lutino", "notas": ""},
    {"id": None, "nombre": "Mushu", "color": "gris plomo", "notas": ""},
]

AREA_MINIMA = 800
AREA_MAXIMA = 150_000
CONF_NINFA = 0.20
CONF_PLATOS = 0.35
DETECT_INTERVALO = 0.10
PERSISTENCIA_CAJAS = 1.5


try:
    from modulos.base_datos import (
        _cargar_config_azure,
        cerrar_cola_escritura,
        obtener_aves,
        obtener_cola_escritura,
        obtener_estado_salud_inicial,
    )

    DB_ACTIVA = bool(_cargar_config_azure())
except Exception as error:
    print(f"Base de datos no disponible: {error}")
    cerrar_cola_escritura = None
    obtener_cola_escritura = None
    obtener_estado_salud_inicial = None
    obtener_aves = None
    DB_ACTIVA = False


COLA_BD = None


def guardar_async(
    categoria: str,
    accion: str,
    valor: float,
    estado: str,
    confianza: float,
    notas: str = "",
    ave_id: int | None = None,
    track_id: int | None = None,
) -> None:
    """Encola un registro sin bloquear el procesamiento de video."""
    if not DB_ACTIVA or COLA_BD is None:
        return
    COLA_BD.encolar(
        [
            (
                categoria,
                accion,
                valor,
                estado,
                confianza,
                notas,
                ave_id,
                track_id,
            )
        ]
    )


def guardar_filas_async(filas: list[tuple]) -> None:
    """Encola un lote de registros sin bloquear el video."""
    if not DB_ACTIVA or COLA_BD is None or not filas:
        return
    COLA_BD.encolar(filas)


def seleccionar_fuente_video() -> tuple[str | int, str | None]:
    """Devuelve la única fuente que utilizarán video y, si aplica, audio."""
    fuente = resolver_fuente()
    print(f"Fuente de video: {describir_fuente(fuente)}.")
    return fuente, fuente if es_rtsp(fuente) else None


def cargar_modelo() -> YOLO:
    if not MODELO_RUTA.is_file():
        raise FileNotFoundError(f"No se encontró el modelo: {MODELO_RUTA}")
    print("Cargando modelo YOLO...")
    return YOLO(str(MODELO_RUTA))


def configurar_identificacion() -> tuple[IdentificadorColor, list[str]]:
    """Configura una única implementación de identidad por color."""
    aves = []
    if DB_ACTIVA and obtener_aves is not None:
        try:
            aves = obtener_aves()
        except Exception as error:
            print(f"No fue posible cargar las aves registradas: {error}")

    aves_para_identidad = aves or AVES_PREDETERMINADAS
    nombres = [ave["nombre"] for ave in aves_para_identidad]
    identificador = IdentificadorColor()

    if identificador.configurar(aves_para_identidad):
        mapeo = ", ".join(
            f"{tipo} -> {ave['nombre']}"
            for tipo, ave in identificador.tipo_a_ave.items()
        )
        print(f"Identificación por color activa: {mapeo}")
    else:
        print("Identificación individual inactiva: faltan colores distinguibles.")

    return identificador, nombres


def inferir(modelo: YOLO, frame, tracking_activo: bool):
    """Ejecuta tracking y permite degradar a detección simple."""
    if tracking_activo:
        try:
            resultados = modelo.track(
                frame,
                persist=True,
                verbose=False,
                conf=min(CONF_NINFA, CONF_PLATOS),
                iou=0.5,
                tracker=TRACKER_CONFIG,
            )
            return resultados, True
        except Exception as error:
            print(f"Tracking no disponible; se usará detección simple: {error}")

    resultados = modelo.predict(
        frame,
        verbose=False,
        conf=min(CONF_NINFA, CONF_PLATOS),
        iou=0.5,
    )
    return resultados, False


def crear_observaciones_comportamiento(
    resultado: ResultadoVision,
    zonas: GestorZonas,
    movimiento: MovementMonitor,
) -> list[ObservacionComportamiento]:
    """Convierte zonas y movimiento en una observación por track."""
    en_comedero, en_bebedero = zonas.evaluar(resultado.aves)
    observaciones = []
    for indice, ave in enumerate(resultado.aves_info):
        if ave.track_id is None:
            continue

        esta_en_comedero = bool(en_comedero[indice])
        esta_en_bebedero = bool(en_bebedero[indice])
        if esta_en_comedero and esta_en_bebedero:
            # Una superposición de zonas es ambigua: es más seguro esperar
            # otra observación que registrar comida o agua incorrectamente.
            estado = EstadoComportamiento.DESCONOCIDO
        elif esta_en_comedero:
            estado = EstadoComportamiento.COMIENDO
        elif esta_en_bebedero:
            estado = EstadoComportamiento.BEBIENDO
        else:
            nivel, _distancia = movimiento.get_activity_level(ave.track_id)
            if nivel in {"Muy Activo", "Normal"}:
                estado = EstadoComportamiento.ACTIVO
            elif nivel == "Sedentario":
                estado = EstadoComportamiento.INACTIVO
            else:
                estado = EstadoComportamiento.DESCONOCIDO

        observaciones.append(
            ObservacionComportamiento(
                track_id=ave.track_id,
                estado=estado,
                confianza=ave.confianza,
                ave_id=ave.ave_id,
                nombre_ave=ave.nombre,
            )
        )
    return observaciones


def procesar_eventos_comportamiento(
    eventos: list[EventoComportamiento], salud: HealthMonitor
) -> None:
    """Actualiza salud y persiste cada transición emitida por la máquina."""
    for evento in eventos:
        ave = evento.nombre_ave or f"track #{evento.track_id}"
        if evento.tipo == TipoEvento.INICIO and evento.estado in {
            EstadoComportamiento.COMIENDO,
            EstadoComportamiento.BEBIENDO,
        }:
            salud.register_action(evento.accion_bd, evento.nombre_ave)

        valor = evento.duracion if evento.tipo == TipoEvento.FIN else 1.0
        print(
            f"{evento.tipo.value.upper()} {evento.estado.value}: "
            f"{evento.duracion:.1f}s [{ave}]"
        )
        guardar_async(
            evento.categoria_bd,
            evento.accion_bd,
            float(valor),
            evento.tipo.value,
            float(evento.confianza),
            (
                f"Estado={evento.estado.value} | Duracion={evento.duracion:.1f}s "
                f"| Ave={ave} | Motivo={evento.motivo}"
            ),
            evento.ave_id,
            evento.track_id,
        )


def calcular_animo(audio: dict, actividad: str, alertas: list[dict]) -> str:
    gritando = audio["status"] == "Gritando"
    actividad_alta = actividad in {"Alta Actividad", "Muy Activo"}
    if alertas and gritando:
        return "Desesperado"
    if gritando and actividad_alta:
        return "Estresado"
    if actividad == "Tranquilo" and audio["status"] in {
        "Sonidos",
        "Silencio",
        "Sin audio",
    }:
        return "Comodo"
    return "Normal"


def dibujar_hud(
    frame,
    accion: str,
    fps: float,
    audio: dict,
    actividad: str,
    animo: str,
    alertas: list[dict],
    recomendaciones: list[str],
) -> None:
    alto, ancho = frame.shape[:2]
    color_texto = (220, 220, 220)
    color_animo = {
        "Comodo": (255, 255, 0),
        "Normal": (0, 255, 0),
        "Estresado": (0, 165, 255),
        "Desesperado": (0, 0, 255),
    }.get(animo, (0, 255, 0))

    cv2.putText(
        frame,
        f"FPS: {fps:.1f}",
        (max(10, ancho - 120), 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
    )
    cv2.putText(
        frame,
        f"Audio: {audio['status']} ({audio['rms']:.3f})",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color_texto,
        1,
    )
    cv2.putText(
        frame,
        f"Actividad: {actividad}",
        (10, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color_texto,
        1,
    )
    cv2.putText(
        frame,
        f"Estado: {animo.upper()}",
        (10, 85),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color_animo,
        2,
    )

    y_alerta = 115
    for alerta in alertas:
        cv2.putText(
            frame,
            alerta["texto"],
            (10, y_alerta),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
        )
        y_alerta += 25

    if accion:
        texto = accion.upper()
        (ancho_texto, _), _ = cv2.getTextSize(
            texto, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2
        )
        cv2.putText(
            frame,
            texto,
            ((ancho - ancho_texto) // 2, 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 255),
            2,
        )

    if recomendaciones:
        cv2.putText(
            frame,
            f"Consejo: {recomendaciones[0]}",
            (10, alto - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (200, 255, 200),
            1,
        )


def iniciar_monitoreo() -> None:
    global COLA_BD

    modelo = cargar_modelo()
    fuente_video, url_audio = seleccionar_fuente_video()
    identificador, nombres_aves = configurar_identificacion()

    procesador_vision = ProcesadorDetecciones(
        nombres_clases=modelo.names,
        confianza_ninfa=CONF_NINFA,
        confianza_platos=CONF_PLATOS,
        area_minima=AREA_MINIMA,
        area_maxima=AREA_MAXIMA,
    )
    visualizador = VisualizadorDetecciones()
    zonas = GestorZonas()

    camara = CamaraStream(fuente_video)
    audio_monitor = AudioMonitor(url_audio) if url_audio else AudioMonitorNulo()
    movimiento = MovementMonitor()
    estado_salud = {}
    if DB_ACTIVA and obtener_cola_escritura is not None:
        COLA_BD = obtener_cola_escritura()
        if obtener_estado_salud_inicial is not None:
            estado_salud = obtener_estado_salud_inicial()
    salud = HealthMonitor(nombres_aves, estado_inicial=estado_salud)
    estabilizador_animo = EstabilizadorAnimo(segundos_confirmacion=10.0)
    snapshot = SnapshotPeriodico(intervalo_segundos=300)
    comportamiento = GestorComportamiento()

    tracking_activo = True
    vision_memoria: ResultadoVision | None = None
    ultima_deteccion = 0.0
    ultima_inferencia = 0.0
    ultimo_frame_id = -1
    tiempo_frame_anterior = time.time()
    fps = 0.0
    recomendaciones = []
    alertas_guardadas: set[str] = set()

    print(f"Base de datos: {'configurada' if DB_ACTIVA else 'modo local sin SQL'}.")
    print("Iniciando monitor. Presiona q para salir.")
    camara.start()
    audio_monitor.start()

    try:
        while True:
            frame_id, frame = camara.leer()
            if frame is None:
                time.sleep(0.05)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            if frame_id == ultimo_frame_id:
                time.sleep(0.005)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue
            ultimo_frame_id = frame_id

            ahora = time.time()
            delta = ahora - tiempo_frame_anterior
            fps = 1.0 / delta if delta > 0 else 0.0
            tiempo_frame_anterior = ahora

            if (ahora - ultima_inferencia) >= DETECT_INTERVALO:
                ultima_inferencia = ahora
                resultados, tracking_activo = inferir(modelo, frame, tracking_activo)
                resultado_vision = procesador_vision.procesar(
                    resultados,
                    frame,
                    identificador,
                    movimiento,
                )
                zonas.actualizar(
                    resultado_vision.comederos,
                    resultado_vision.bebederos,
                    frame.shape,
                )
                observaciones = crear_observaciones_comportamiento(
                    resultado_vision,
                    zonas,
                    movimiento,
                )
                eventos = comportamiento.actualizar(observaciones, ahora)
                procesar_eventos_comportamiento(eventos, salud)

                if len(resultado_vision.detecciones):
                    vision_memoria = resultado_vision
                    ultima_deteccion = ahora
                elif (ahora - ultima_deteccion) > PERSISTENCIA_CAJAS:
                    vision_memoria = None

            audio = audio_monitor.get_status()
            actividad, valor_actividad = movimiento.get_global_activity()
            alertas = salud.check_health()
            animo_instantaneo = calcular_animo(audio, actividad, alertas)
            animo, cambio_animo = estabilizador_animo.actualizar(animo_instantaneo)

            if cambio_animo:
                print(f"Cambio de ánimo: {animo}")
                guardar_async(
                    "Estado",
                    "CambioAnimo",
                    0.0,
                    animo,
                    1.0,
                    f"Audio={audio['status']} | Actividad={actividad}",
                )

            tipos_alerta = {alerta["tipo"] for alerta in alertas}
            for alerta in alertas:
                if alerta["tipo"] not in alertas_guardadas:
                    alertas_guardadas.add(alerta["tipo"])
                    print(f"Alerta de salud: {alerta['texto']}")
                    guardar_async(
                        "Salud",
                        alerta["tipo"],
                        float(alerta["horas"]),
                        "Alerta",
                        0.0,
                        alerta["texto"],
                    )
            alertas_guardadas &= tipos_alerta

            estadisticas_salud = salud.get_stats()
            horas_sin_comer = estadisticas_salud["eating_sec"] / 3600.0
            horas_sin_beber = estadisticas_salud["drinking_sec"] / 3600.0
            recomendaciones = generar_recomendaciones(
                animo,
                actividad,
                horas_sin_comer,
                horas_sin_beber,
                audio["status"],
            )

            if snapshot.toca_guardar():
                filas = snapshot.armar_filas(
                    animo,
                    actividad,
                    valor_actividad,
                    audio,
                    estadisticas_salud,
                )
                filas.extend(
                    (
                        "Recomendacion",
                        recomendacion,
                        0.0,
                        animo,
                        1.0,
                        f"Audio={audio['status']} | Actividad={actividad}",
                    )
                    for recomendacion in recomendaciones
                )
                guardar_filas_async(filas)

            if vision_memoria is not None:
                frame = visualizador.anotar(frame, vision_memoria)
            frame = zonas.anotar(frame)

            dibujar_hud(
                frame,
                comportamiento.resumen(),
                fps,
                audio,
                actividad,
                animo,
                alertas,
                recomendaciones,
            )
            cv2.imshow("Monitor de Ninfas", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        eventos_finales = comportamiento.cerrar_todos(time.time())
        procesar_eventos_comportamiento(eventos_finales, salud)
        print("Deteniendo monitor...")
        audio_monitor.stop()
        camara.stop()
        cv2.destroyAllWindows()
        if cerrar_cola_escritura is not None:
            cerrar_cola_escritura()
        COLA_BD = None


if __name__ == "__main__":
    try:
        iniciar_monitoreo()
    except KeyboardInterrupt:
        print("Monitor interrumpido por el usuario.")
    except Exception as error:
        print(f"No fue posible iniciar el monitor: {error}")
        raise
