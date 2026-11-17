"""Orquestador del Monitor de Ninfas.

Coordina una fuente de video, YOLO/BoT-SORT, Supervision, identidad por color,
máquinas de estado por track, audio, salud y persistencia asíncrona.
"""

from __future__ import annotations

import os
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
from modulos.captura_activa import RecolectorActivoDataset
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
from modulos.notificaciones import NotificadorAlertas
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
_TRACKER_LOCAL = RAIZ / "botsort_ninfas.yaml"
TRACKER_CONFIG = (
    str(_TRACKER_LOCAL) if _TRACKER_LOCAL.is_file() else "botsort.yaml"
)

AVES_PREDETERMINADAS = [
    {"id": None, "nombre": "Yukki", "color": "amarilla lutino", "notas": ""},
    {"id": None, "nombre": "Mushu", "color": "gris plomo", "notas": ""},
]

AREA_MINIMA = 800
AREA_MAXIMA = 85_000
CONF_NINFA = 0.55
CONF_PLATOS = 0.55
CONF_CAPTURA_ACTIVA = 0.25
IMGSZ_INFERENCIA = 512
DETECT_INTERVALO = 0.0
PERSISTENCIA_CAJAS = 1.5
FPS_OBJETIVO = 20.0


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


def es_modo_headless() -> bool:
    """Permite operar en un mini-servidor dedicado sin ventana gráfica OpenCV."""
    return os.getenv("NINFAS_HEADLESS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
    }


def audio_rtsp_habilitado() -> bool:
    """Permite desactivar el segundo stream RTSP de audio si la cámara limita sesiones."""
    return os.getenv("NINFAS_AUDIO_RTSP", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def seleccionar_fuente_video() -> tuple[str | int, str | None]:
    """Devuelve la única fuente que utilizarán video y, si aplica, audio."""
    fuente = resolver_fuente()
    print(f"Fuente de video: {describir_fuente(fuente)}.")
    usar_audio = es_rtsp(fuente) and audio_rtsp_habilitado()
    return fuente, fuente if usar_audio else None


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


def sincronizar_aves_en_caliente(
    identificador: IdentificadorColor, salud: HealthMonitor
) -> None:
    """Recarga aves desde Azure SQL sin perder los votos de tracking activos."""
    if not DB_ACTIVA or obtener_aves is None:
        return
    try:
        aves = obtener_aves()
    except Exception:
        return
    if not aves:
        return
    cambio_id = identificador.sincronizar_aves(aves)
    cambio_salud = salud.sincronizar_aves([ave["nombre"] for ave in aves])
    if cambio_id or cambio_salud:
        mapeo = ", ".join(
            f"{tipo} -> {ave['nombre']} (id={ave['id']})"
            for tipo, ave in identificador.tipo_a_ave.items()
        )
        print(f"Aves sincronizadas en caliente desde Azure SQL: {mapeo}")


def inferir(modelo: YOLO, frame, tracking_activo: bool):
    """Ejecuta tracking y permite degradar a detección simple."""
    auto_dataset = os.getenv("NINFAS_AUTO_DATASET", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
    }
    conf_min = (
        min(CONF_NINFA, CONF_PLATOS, CONF_CAPTURA_ACTIVA)
        if auto_dataset
        else min(CONF_NINFA, CONF_PLATOS)
    )
    if tracking_activo:
        try:
            resultados = modelo.track(
                frame,
                persist=True,
                verbose=False,
                imgsz=IMGSZ_INFERENCIA,
                conf=conf_min,
                iou=0.5,
                tracker=TRACKER_CONFIG,
            )
            return resultados, True
        except Exception as error:
            print(f"Tracking no disponible; se usará detección simple: {error}")

    resultados = modelo.predict(
        frame,
        verbose=False,
        imgsz=IMGSZ_INFERENCIA,
        conf=conf_min,
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
    eventos: list[EventoComportamiento],
    salud: HealthMonitor,
    recolector_activo: RecolectorActivoDataset | None = None,
) -> None:
    """Actualiza salud y persiste las transiciones relevantes emitidas por la máquina."""
    for evento in eventos:
        ave = evento.nombre_ave or f"track #{evento.track_id}"
        es_consumo = evento.estado in {
            EstadoComportamiento.COMIENDO,
            EstadoComportamiento.BEBIENDO,
        }
        if evento.tipo in {TipoEvento.INICIO, TipoEvento.FIN} and es_consumo:
            salud.register_action(evento.accion_bd, evento.nombre_ave)

        valor = evento.duracion if evento.tipo == TipoEvento.FIN else 1.0
        print(
            f"{evento.tipo.value.upper()} {evento.estado.value}: "
            f"{evento.duracion:.1f}s [{ave}]"
        )
        if not es_consumo:
            continue
        notas = (
            f"Estado={evento.estado.value} | Duracion={evento.duracion:.1f}s "
            f"| Ave={ave} | Motivo={evento.motivo}"
        )
        if recolector_activo is not None:
            ruta_evidencia = recolector_activo.guardar_evidencia_evento(
                evento.estado.value,
                evento.tipo.value,
                evento.track_id,
                evento.nombre_ave,
                ahora=evento.timestamp,
            )
            if ruta_evidencia is not None:
                notas += f" | Evidencia={ruta_evidencia.name}"
        guardar_async(
            evento.categoria_bd,
            evento.accion_bd,
            float(valor),
            evento.tipo.value,
            float(evento.confianza),
            notas,
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
    fps_yolo: float = 0.0,
) -> None:
    alto, ancho = frame.shape[:2]
    color_texto = (220, 220, 220)
    color_animo = {
        "Comodo": (255, 255, 0),
        "Normal": (0, 255, 0),
        "Estresado": (0, 165, 255),
        "Desesperado": (0, 0, 255),
    }.get(animo, (0, 255, 0))

    texto_fps = (
        f"FPS: {fps:.1f} | IA: {fps_yolo:.1f}" if fps_yolo > 0 else f"FPS: {fps:.1f}"
    )
    cv2.putText(
        frame,
        texto_fps,
        (max(10, ancho - 210 if fps_yolo > 0 else ancho - 120), 30),
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
    snapshot = SnapshotPeriodico()
    comportamiento = GestorComportamiento()
    notificador = NotificadorAlertas()
    recolector_activo = RecolectorActivoDataset()

    tracking_activo = True
    vision_memoria: ResultadoVision | None = None
    ultima_deteccion = 0.0
    ultima_inferencia = 0.0
    ultimo_frame_id = -1
    frame_actual = None
    ultimo_frame_mostrado = None
    tiempo_frame_anterior = time.perf_counter()
    fps = FPS_OBJETIVO
    fps_yolo = 0.0
    ultimo_yolo_ts: float | None = None
    intervalo_ui = 1.0 / FPS_OBJETIVO
    recomendaciones = []
    alertas_guardadas: set[str] = set()
    headless = es_modo_headless()

    print(f"Base de datos: {'configurada' if DB_ACTIVA else 'modo local sin SQL'}.")
    print(f"Modo de interfaz: {'headless (servidor dedicado)' if headless else 'ventana OpenCV'}.")
    print("Iniciando monitor. Presiona q para salir." if not headless else "Iniciando monitor headless (Ctrl+C para detener).")
    camara.start()
    audio_monitor.start()

    try:
        while True:
            inicio_ciclo = time.perf_counter()
            ahora = time.monotonic()
            estado_camara = camara.estado()
            frame_id, nuevo_frame = camara.leer()
            camara_conectada = (
                bool(estado_camara.get("conectada", False))
                and nuevo_frame is not None
            )

            if camara_conectada:
                frame_actual = nuevo_frame
                ultimo_frame_mostrado = nuevo_frame
                recolector_activo.registrar_frame(frame_actual, ahora)
            else:
                frame_actual = None
                vision_memoria = None
                procesador_vision.recoger_resultado_async()
                eventos = comportamiento.actualizar([], ahora)
                procesar_eventos_comportamiento(
                    eventos, salud, recolector_activo=recolector_activo
                )

            if frame_actual is None and ultimo_frame_mostrado is None:
                time.sleep(0.02)
                if not headless and (cv2.waitKey(1) & 0xFF == ord("q")):
                    break
                continue

            if headless and camara_conectada and frame_id == ultimo_frame_id:
                time.sleep(0.01)
                continue

            if camara_conectada:
                if (
                    frame_id != ultimo_frame_id
                    and (ahora - ultima_inferencia) >= DETECT_INTERVALO
                ):
                    ultimo_frame_id = frame_id
                    ultima_inferencia = ahora
                    procesador_vision.enviar_frame_async(
                        frame_actual,
                        frame_id,
                        lambda f, ta=tracking_activo: inferir(modelo, f, ta),
                    )

                paquete_yolo = procesador_vision.recoger_resultado_async()
                if paquete_yolo is not None:
                    if ultimo_yolo_ts is not None and (ahora - ultimo_yolo_ts) > 0:
                        inst_yolo = 1.0 / (ahora - ultimo_yolo_ts)
                        fps_yolo = (
                            inst_yolo
                            if fps_yolo == 0.0
                            else (0.85 * fps_yolo + 0.15 * inst_yolo)
                        )
                    ultimo_yolo_ts = ahora
                    resultados, tracking_activo, frame_inferido, _fid = paquete_yolo
                    resultado_vision = procesador_vision.procesar(
                        resultados,
                        frame_inferido,
                        identificador,
                        movimiento,
                    )
                    zonas.actualizar(
                        resultado_vision.comederos,
                        resultado_vision.bebederos,
                        frame_inferido.shape,
                        ahora=ahora,
                    )
                    observaciones = crear_observaciones_comportamiento(
                        resultado_vision,
                        zonas,
                        movimiento,
                    )
                    eventos = comportamiento.actualizar(observaciones, ahora)
                    procesar_eventos_comportamiento(
                        eventos, salud, recolector_activo=recolector_activo
                    )
                    recolector_activo.evaluar_y_guardar(
                        frame_inferido,
                        resultado_vision,
                        resultados_crudos=resultados,
                    )

                    if len(resultado_vision.detecciones):
                        vision_memoria = resultado_vision
                        ultima_deteccion = ahora
                    elif (ahora - ultima_deteccion) > PERSISTENCIA_CAJAS:
                        vision_memoria = None
                elif (
                    vision_memoria is not None
                    and (ahora - ultima_deteccion) > PERSISTENCIA_CAJAS
                ):
                    vision_memoria = None

            audio = audio_monitor.get_status()
            actividad, valor_actividad = movimiento.get_global_activity()
            luz_diurna = (
                IdentificadorColor.frame_tiene_color(frame_actual)
                if (camara_conectada and frame_actual is not None)
                else False
            )
            salud.actualizar_condiciones(
                camara_conectada=camara_conectada,
                luz_diurna=luz_diurna,
            )
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
                if animo == "Desesperado":
                    notificador.notificar_async(
                        "animo:Desesperado",
                        f"Estado DESESPERADO detectado (Audio={audio['status']}, Actividad={actividad})",
                        nivel="critica",
                    )

            tipos_alerta = {alerta["tipo"] for alerta in alertas}
            for alerta in alertas:
                if alerta["tipo"] not in alertas_guardadas:
                    alertas_guardadas.add(alerta["tipo"])
                    nivel_alerta = alerta.get("nivel", "critica")
                    estado_alerta = (
                        "Vigilancia"
                        if nivel_alerta == "vigilancia"
                        else "Alerta"
                    )
                    print(f"Alerta de salud ({estado_alerta}): {alerta['texto']}")
                    guardar_async(
                        "Salud",
                        alerta["tipo"],
                        float(alerta["horas"]),
                        estado_alerta,
                        0.0,
                        alerta["texto"],
                    )
                    notificador.notificar_async(
                        alerta["tipo"],
                        alerta["texto"],
                        nivel=nivel_alerta,
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

            if camara_conectada and snapshot.toca_guardar():
                sincronizar_aves_en_caliente(identificador, salud)
                filas = snapshot.armar_filas(
                    animo,
                    actividad,
                    valor_actividad,
                    audio,
                    estadisticas_salud,
                )
                guardar_filas_async(filas)

            if not headless:
                base_canvas = (
                    frame_actual
                    if frame_actual is not None
                    else ultimo_frame_mostrado
                )
                canvas = base_canvas.copy()
                if vision_memoria is not None:
                    canvas = visualizador.anotar(
                        canvas, vision_memoria, frame_id=frame_id
                    )
                if camara_conectada:
                    canvas = zonas.anotar(canvas)

                texto_accion = (
                    comportamiento.resumen()
                    if camara_conectada
                    else "CAMARA DESCONECTADA"
                )
                dibujar_hud(
                    canvas,
                    texto_accion,
                    fps,
                    audio,
                    actividad,
                    animo,
                    alertas,
                    recomendaciones,
                    fps_yolo=fps_yolo,
                )
                cv2.imshow("Monitor de Ninfas", canvas)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

                restante = intervalo_ui - (time.perf_counter() - inicio_ciclo)
                if restante > 0:
                    time.sleep(restante)

                ahora_perf = time.perf_counter()
                delta_ui = ahora_perf - tiempo_frame_anterior
                tiempo_frame_anterior = ahora_perf
                if delta_ui > 0:
                    fps = 0.85 * fps + 0.15 * (1.0 / delta_ui)
            elif not camara_conectada:
                time.sleep(0.02)
    finally:
        eventos_finales = comportamiento.cerrar_todos(time.monotonic())
        procesar_eventos_comportamiento(
            eventos_finales, salud, recolector_activo=recolector_activo
        )
        print("Deteniendo monitor...")
        procesador_vision.detener_worker_async()
        recolector_activo.stop()
        audio_monitor.stop()
        camara.stop()
        notificador.stop()
        if not headless:
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
