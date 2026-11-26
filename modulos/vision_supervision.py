"""Capa de postprocesamiento visual basada en Roboflow Supervision.

Convierte resultados Ultralytics a ``sv.Detections``, aplica los filtros de
clase/confianza, mantiene metadatos por ave y dibuja cajas, etiquetas, trazas y
zonas. El tracking continúa siendo responsabilidad de Ultralytics/BoT-SORT.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import supervision as sv


@dataclass(slots=True)
class AveEnFrame:
    coords: tuple[int, int, int, int]
    confianza: float
    track_id: int | None
    ave_id: int | None
    nombre: str | None


@dataclass(slots=True)
class ResultadoVision:
    detecciones: sv.Detections
    aves: sv.Detections
    comederos: sv.Detections
    bebederos: sv.Detections
    etiquetas: list[str]
    aves_info: list[AveEnFrame]


def _mapa_clases(nombres: dict[int, str] | list[str]) -> dict[str, int]:
    elementos = nombres.items() if isinstance(nombres, dict) else enumerate(nombres)
    return {str(nombre).strip().lower(): int(indice) for indice, nombre in elementos}


class ProcesadorDetecciones:
    """Adapta RF-DETR/BoT-SORT al formato común de Supervision."""

    CLASES_AVES_ACTIVAS = ("mushu", "yukki")
    CLASES_AVES_AUXILIARES = ("shiro", "ninfa")
    FRAC_MIN = 0.0005
    FRAC_MAX_NINFA = 0.22
    FRAC_MAX_PLATOS = 0.08
    IOU_COLISION_CLASES = 0.45
    COBERTURA_MIN_OCLUSION_NINFAS = 0.20

    def __init__(
        self,
        nombres_clases: dict[int, str] | list[str],
        confianza_ninfa: float,
        confianza_platos: float,
        area_minima: int | None = None,
        area_maxima: int | None = None,
    ) -> None:
        clases = _mapa_clases(nombres_clases)
        faltantes_platos = {"comedero", "bebedero"} - clases.keys()
        tiene_aves_v6 = set(self.CLASES_AVES_ACTIVAS).issubset(clases.keys())
        tiene_ninfa_legado = "ninfa" in clases
        if faltantes_platos or (not tiene_aves_v6 and not tiene_ninfa_legado):
            faltantes = set(faltantes_platos)
            if not tiene_aves_v6 and not tiene_ninfa_legado:
                faltantes.update(self.CLASES_AVES_ACTIVAS)
            raise ValueError(
                "El modelo no contiene las clases requeridas: "
                + ", ".join(sorted(faltantes))
            )

        self.id_comedero = clases["comedero"]
        self.id_bebedero = clases["bebedero"]
        self.id_shiro = clases.get("shiro")
        self.ids_aves_individuales: tuple[int, ...] = tuple(
            clases[nombre]
            for nombre in self.CLASES_AVES_ACTIVAS
            if nombre in clases
        )
        self.ids_aves_auxiliares: tuple[int, ...] = tuple(
            clases[nombre]
            for nombre in self.CLASES_AVES_AUXILIARES
            if nombre in clases
        )
        self.id_a_clase_ave: dict[int, str] = {
            clases[nombre]: nombre
            for nombre in (*self.CLASES_AVES_ACTIVAS, *self.CLASES_AVES_AUXILIARES)
            if nombre in clases
        }
        self.ids_aves: tuple[int, ...] = tuple(sorted(self.id_a_clase_ave))
        self.confianza_ninfa = confianza_ninfa
        self.confianza_platos = confianza_platos
        self.area_minima = area_minima
        self.area_maxima = area_maxima

        # Cola de 1 elemento (último frame) para inferencia asíncrona no bloqueante
        self._lock_async = threading.Lock()
        self._evento_async = threading.Event()
        self._corriendo_async = False
        self._hilo_async: threading.Thread | None = None
        self._tarea_pendiente: tuple[np.ndarray, int, Callable] | None = None
        self._resultado_listo: tuple[Any, bool, np.ndarray, int] | None = None

    def iniciar_worker_async(self) -> None:
        if self._corriendo_async:
            return
        self._corriendo_async = True
        self._hilo_async = threading.Thread(
            target=self._bucle_worker_async,
            name="yolo-tracker-worker",
            daemon=True,
        )
        self._hilo_async.start()

    def detener_worker_async(self) -> None:
        self._corriendo_async = False
        self._evento_async.set()
        if self._hilo_async and self._hilo_async.is_alive():
            self._hilo_async.join(timeout=2)
        self._hilo_async = None

    def enviar_frame_async(
        self, frame: np.ndarray, frame_id: int, fn_inferir: Callable
    ) -> None:
        """Entrega el frame más reciente al hilo de YOLO sin bloquear la UI."""
        self.iniciar_worker_async()
        with self._lock_async:
            self._tarea_pendiente = (frame.copy(), frame_id, fn_inferir)
        self._evento_async.set()

    def recoger_resultado_async(
        self,
    ) -> tuple[Any, bool, np.ndarray, int] | None:
        """Retorna el último resultado de YOLO si ya terminó, o None de inmediato."""
        with self._lock_async:
            res = self._resultado_listo
            self._resultado_listo = None
            return res

    def _bucle_worker_async(self) -> None:
        while self._corriendo_async:
            self._evento_async.wait(timeout=0.1)
            self._evento_async.clear()
            if not self._corriendo_async:
                break
            with self._lock_async:
                tarea = self._tarea_pendiente
                self._tarea_pendiente = None
            if tarea is None:
                continue
            frame, frame_id, fn_inferir = tarea
            try:
                resultados, tracking_activo = fn_inferir(frame)
                with self._lock_async:
                    self._resultado_listo = (
                        resultados,
                        tracking_activo,
                        frame,
                        frame_id,
                    )
            except Exception as error:
                print(f"Error en worker de inferencia: {error}")

    @staticmethod
    def _iou_cajas(caja_a: np.ndarray, caja_b: np.ndarray) -> float:
        x1 = max(float(caja_a[0]), float(caja_b[0]))
        y1 = max(float(caja_a[1]), float(caja_b[1]))
        x2 = min(float(caja_a[2]), float(caja_b[2]))
        y2 = min(float(caja_a[3]), float(caja_b[3]))
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if inter <= 0.0:
            return 0.0
        area_a = max(0.0, float(caja_a[2] - caja_a[0])) * max(
            0.0, float(caja_a[3] - caja_a[1])
        )
        area_b = max(0.0, float(caja_b[2] - caja_b[0])) * max(
            0.0, float(caja_b[3] - caja_b[1])
        )
        union = area_a + area_b - inter
        return inter / union if union > 0.0 else 0.0

    def _filtrar_colisiones_ave_plato(
        self, xyxy: np.ndarray, clases: np.ndarray, confianzas: np.ndarray
    ) -> np.ndarray:
        """Suprime colisiones entre platos y duplicados fantasma de 'shiro' sobre aves activas."""
        conservar = np.ones(len(clases), dtype=bool)
        idx_comederos = np.flatnonzero(clases == self.id_comedero)
        idx_bebederos = np.flatnonzero(clases == self.id_bebedero)
        for i_com in idx_comederos:
            for i_beb in idx_bebederos:
                iou = self._iou_cajas(xyxy[i_com], xyxy[i_beb])
                if iou >= self.IOU_COLISION_CLASES:
                    if confianzas[i_com] >= confianzas[i_beb]:
                        conservar[i_beb] = False
                    else:
                        conservar[i_com] = False

        if self.ids_aves_individuales and self.ids_aves_auxiliares:
            idx_aux = np.flatnonzero(np.isin(clases, self.ids_aves_auxiliares))
            idx_activas = np.flatnonzero(np.isin(clases, self.ids_aves_individuales))
            for i_aux in idx_aux:
                for i_act in idx_activas:
                    if self._iou_cajas(xyxy[i_aux], xyxy[i_act]) >= self.IOU_COLISION_CLASES:
                        conservar[i_aux] = False
                        break
        return conservar

    def _indices_aves_ocultas(
        self, xyxy: np.ndarray, indices_aves: np.ndarray
    ) -> set[int]:
        """Marca ambos miembros de cada par mezclado, incluso si uno está contenido."""
        dimensiones = np.maximum(0.0, xyxy[:, 2:] - xyxy[:, :2])
        areas = dimensiones[:, 0] * dimensiones[:, 1]
        ocultas: set[int] = set()
        for posicion, indice in enumerate(indices_aves):
            for otro in indices_aves[posicion + 1:]:
                area_menor = min(areas[indice], areas[otro])
                if area_menor <= 0.0:
                    continue
                dimensiones_inter = np.maximum(
                    0.0,
                    np.minimum(xyxy[indice, 2:], xyxy[otro, 2:])
                    - np.maximum(xyxy[indice, :2], xyxy[otro, :2]),
                )
                interseccion = float(dimensiones_inter[0] * dimensiones_inter[1])
                if interseccion >= area_menor * self.COBERTURA_MIN_OCLUSION_NINFAS:
                    ocultas.update((int(indice), int(otro)))
        return ocultas

    def procesar(
        self,
        resultados: list[Any],
        frame: np.ndarray,
        identificador,
        movimiento,
    ) -> ResultadoVision:
        if not resultados:
            raise ValueError("Ultralytics no devolvió un resultado para el frame.")

        detecciones = sv.Detections.from_ultralytics(resultados[0])
        if len(detecciones) == 0:
            vacias = detecciones[np.zeros(0, dtype=bool)]
            return ResultadoVision(vacias, vacias, vacias, vacias, [], [])

        if detecciones.class_id is None:
            raise ValueError("Las detecciones no contienen identificadores de clase.")

        clases = detecciones.class_id.astype(int)
        confianzas = (
            detecciones.confidence
            if detecciones.confidence is not None
            else np.ones(len(detecciones), dtype=float)
        )
        anchos = np.maximum(0.0, detecciones.xyxy[:, 2] - detecciones.xyxy[:, 0])
        altos = np.maximum(0.0, detecciones.xyxy[:, 3] - detecciones.xyxy[:, 1])
        areas = anchos * altos
        alto_frame, ancho_frame = frame.shape[:2]
        area_frame = float(max(1, alto_frame * ancho_frame))
        frac_areas = areas / area_frame

        es_ave = np.isin(clases, self.ids_aves)
        es_comedero = clases == self.id_comedero
        es_bebedero = clases == self.id_bebedero
        es_plato = es_comedero | es_bebedero
        confianza_valida = (es_ave & (confianzas >= self.confianza_ninfa)) | (
            es_plato & (confianzas >= self.confianza_platos)
        )
        frac_valida = (frac_areas >= self.FRAC_MIN) & (
            (es_ave & (frac_areas <= self.FRAC_MAX_NINFA))
            | (es_plato & (frac_areas <= self.FRAC_MAX_PLATOS))
        )
        sin_colision = self._filtrar_colisiones_ave_plato(
            detecciones.xyxy, clases, confianzas
        )
        mascara = confianza_valida & frac_valida & sin_colision
        detecciones = detecciones[mascara]

        if len(detecciones) == 0:
            vacias = detecciones[np.zeros(0, dtype=bool)]
            return ResultadoVision(vacias, vacias, vacias, vacias, [], [])

        clases = detecciones.class_id.astype(int)
        confianzas = detecciones.confidence
        if confianzas is None:
            confianzas = np.ones(len(detecciones), dtype=float)

        mascara_aves = np.isin(clases, self.ids_aves)
        mascara_comederos = clases == self.id_comedero
        mascara_bebederos = clases == self.id_bebedero
        tracker_ids = detecciones.tracker_id
        indices_aves = np.flatnonzero(mascara_aves)
        aves_ocultas = self._indices_aves_ocultas(detecciones.xyxy, indices_aves)

        alto_frame, ancho_frame = frame.shape[:2]
        datos_aves = {}
        tracks_visibles = []
        for indice in indices_aves:
            indice = int(indice)
            clase_id = int(clases[indice])
            clase_ave = self.id_a_clase_ave.get(clase_id)
            pista_ave = None if clase_ave in {"shiro", "ninfa"} else clase_ave
            confianza = float(confianzas[indice])
            track_id = int(tracker_ids[indice]) if tracker_ids is not None else None
            coords = tuple(detecciones.xyxy[indice].astype(int).tolist())
            datos_aves[indice] = (coords, confianza, track_id, clase_ave, pista_ave)
            if track_id is None:
                continue
            x1, y1, x2, y2 = coords
            movimiento.update(
                track_id,
                (x1 + x2) // 2,
                (y1 + y2) // 2,
                ancho_frame,
                alto_frame,
            )
            if indice in aves_ocultas:
                identificador.suspender(track_id)
                continue
            if clase_ave != "ninfa" and hasattr(identificador, "votar_deteccion"):
                identificador.votar_deteccion(
                    track_id, pista_ave, frame, coords, confianza=confianza
                )
            else:
                identificador.votar(track_id, frame, coords)
            tracks_visibles.append(track_id)

        identidades = identificador.resolver(tracks_visibles)
        etiquetas = []
        aves_info = []
        for indice in range(len(detecciones)):
            clase_id = int(clases[indice])
            confianza = float(confianzas[indice])

            if clase_id in self.id_a_clase_ave:
                coords, confianza, track_id, clase_ave, pista_ave = datos_aves[indice]
                if indice in aves_ocultas:
                    ave_id, nombre_ave = (None, None)
                elif track_id is not None:
                    ave_id, nombre_ave = identidades.get(track_id, (None, None))
                elif hasattr(identificador, "resolver_clase_directa"):
                    ave_id, nombre_ave = identificador.resolver_clase_directa(pista_ave)
                else:
                    ave_id, nombre_ave = (
                        None,
                        pista_ave.capitalize() if pista_ave else None,
                    )

                etiqueta_base = "ninfa" if clase_ave == "ninfa" else "ave"
                etiqueta = nombre_ave or etiqueta_base
                if track_id is not None:
                    etiqueta += f" #{track_id}"
                etiqueta += f" {confianza:.2f}"
                etiquetas.append(etiqueta)
                aves_info.append(
                    AveEnFrame(coords, confianza, track_id, ave_id, nombre_ave)
                )
            elif clase_id == self.id_comedero:
                etiquetas.append(f"comedero {confianza:.2f}")
            else:
                etiquetas.append(f"bebedero {confianza:.2f}")

        return ResultadoVision(
            detecciones=detecciones,
            aves=detecciones[mascara_aves],
            comederos=detecciones[mascara_comederos],
            bebederos=detecciones[mascara_bebederos],
            etiquetas=etiquetas,
            aves_info=aves_info,
        )


class VisualizadorDetecciones:
    """Compone los anotadores oficiales de Supervision con suavizado temporal de cajas."""

    def __init__(self, alpha_suavizado: float = 0.38) -> None:
        self.cajas = sv.BoxAnnotator(thickness=2)
        self.etiquetas = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
        self.trazas = sv.TraceAnnotator(thickness=2, trace_length=30)
        self.alpha_suavizado = float(alpha_suavizado)
        self._cajas_previas: dict[int, np.ndarray] = {}
        self._edad_cajas: dict[int, int] = {}
        self._ultimo_frame_id: int | None = None

    def _suavizar_detecciones(
        self, detecciones: sv.Detections, actualizar_estado: bool = True
    ) -> sv.Detections:
        """Interpola coordenadas xyxy con ganancia adaptativa para fluidez de UI."""
        if (
            len(detecciones) == 0
            or detecciones.tracker_id is None
            or len(detecciones.xyxy) == 0
        ):
            return detecciones

        copia = copy.copy(detecciones)
        nuevas_xyxy = np.array(detecciones.xyxy, dtype=float, copy=True)
        activos = set()
        alfa_base = self.alpha_suavizado
        clases = detecciones.class_id

        for idx, raw_tid in enumerate(detecciones.tracker_id):
            if raw_tid is not None:
                tid = int(raw_tid)
            elif clases is not None and idx < len(clases):
                tid = -(int(clases[idx]) + 1)
            else:
                continue

            activos.add(tid)
            actual = nuevas_xyxy[idx]
            previa = self._cajas_previas.get(tid)
            if not actualizar_estado:
                suavizada = previa if previa is not None else actual
            elif previa is None:
                suavizada = actual
                self._cajas_previas[tid] = suavizada
                self._edad_cajas[tid] = 0
            else:
                desplazamiento = float(np.linalg.norm(actual - previa))
                if desplazamiento < 1.8:
                    # Filtro anti-vibración cuando el ave o plato está quieto
                    alfa = 0.12
                else:
                    # Ganancia adaptativa proporcional a la velocidad (tipo 1-Euro)
                    alfa = min(0.62, alfa_base + (desplazamiento / 120.0))
                suavizada = alfa * actual + (1.0 - alfa) * previa
                self._cajas_previas[tid] = suavizada
                self._edad_cajas[tid] = 0
            nuevas_xyxy[idx] = suavizada

        if actualizar_estado:
            # Conserva tracks brevemente ocultos (hasta ~20 frames UI) para evitar saltos
            for tid in list(self._cajas_previas):
                if tid not in activos:
                    edad = self._edad_cajas.get(tid, 0) + 1
                    if edad > 20:
                        self._cajas_previas.pop(tid, None)
                        self._edad_cajas.pop(tid, None)
                    else:
                        self._edad_cajas[tid] = edad

        copia.xyxy = nuevas_xyxy
        return copia

    def anotar(
        self,
        frame: np.ndarray,
        resultado: ResultadoVision,
        frame_id: int | None = None,
    ) -> np.ndarray:
        if len(resultado.detecciones) == 0:
            self._cajas_previas.clear()
            self._ultimo_frame_id = None
            return frame

        actualizar_estado = (
            True if frame_id is None else (frame_id != self._ultimo_frame_id)
        )
        self._ultimo_frame_id = frame_id
        det_suaves = self._suavizar_detecciones(
            resultado.detecciones, actualizar_estado=actualizar_estado
        )
        if len(resultado.aves) and resultado.aves.tracker_id is not None:
            aves_suaves = self._suavizar_detecciones(
                resultado.aves, actualizar_estado=False
            )
            frame = self.trazas.annotate(scene=frame, detections=aves_suaves)
        frame = self.cajas.annotate(scene=frame, detections=det_suaves)
        return self.etiquetas.annotate(
            scene=frame,
            detections=det_suaves,
            labels=resultado.etiquetas,
        )


def parsear_poligono_normalizado(valor: str | None) -> list[tuple[float, float]] | None:
    """Lee ``x,y;x,y;...`` con coordenadas entre 0 y 1."""
    if not valor or not valor.strip():
        return None

    puntos = []
    for punto in valor.split(";"):
        partes = [parte.strip() for parte in punto.split(",")]
        if len(partes) != 2:
            raise ValueError("cada punto debe tener el formato x,y")
        x, y = map(float, partes)
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError("las coordenadas de zona deben estar entre 0 y 1")
        puntos.append((x, y))

    if len(puntos) < 3:
        raise ValueError("una zona necesita al menos tres puntos")
    return puntos


@dataclass(slots=True)
class ZonaAnotada:
    nombre: str
    zona: sv.PolygonZone
    anotador: sv.PolygonZoneAnnotator


class GestorZonas:
    """Mantiene zonas estáticas normalizadas o derivadas de los platos detectados."""

    TTL_ZONA_DINAMICA = 60.0

    def __init__(
        self,
        margen_dinamico: float = 0.20,
        permitir_dinamicas: bool | None = None,
        ttl_dinamico: float = TTL_ZONA_DINAMICA,
    ) -> None:
        self.margen_dinamico = max(0.0, margen_dinamico)
        if permitir_dinamicas is None:
            valor_env = os.getenv("NINFAS_ZONAS_DINAMICAS", "1").strip().lower()
            permitir_dinamicas = valor_env not in {"0", "false", "no"}
        self.permitir_dinamicas = bool(permitir_dinamicas)
        self.ttl_dinamico = max(0.0, float(ttl_dinamico))
        self.especificacion_comedero = self._leer_zona("ZONA_COMEDERO")
        self.especificacion_bebedero = self._leer_zona("ZONA_BEBEDERO")
        self.resolucion: tuple[int, int] | None = None
        self.zonas_comedero: list[ZonaAnotada] = []
        self.zonas_bebedero: list[ZonaAnotada] = []
        self._ultimo_comedero_ts: float | None = None
        self._ultimo_bebedero_ts: float | None = None

    @staticmethod
    def _leer_zona(nombre: str) -> list[tuple[float, float]] | None:
        try:
            return parsear_poligono_normalizado(os.getenv(nombre))
        except ValueError as error:
            print(f"Zona {nombre} ignorada: {error}")
            return None

    @staticmethod
    def _escalar(
        puntos: list[tuple[float, float]], resolucion: tuple[int, int]
    ) -> np.ndarray:
        ancho, alto = resolucion
        escala = np.array([max(1, ancho - 1), max(1, alto - 1)], dtype=float)
        return np.rint(np.asarray(puntos, dtype=float) * escala).astype(int)

    def _desde_cajas(
        self, detecciones: sv.Detections, resolucion: tuple[int, int]
    ) -> list[np.ndarray]:
        ancho_frame, alto_frame = resolucion
        poligonos = []
        for x1, y1, x2, y2 in detecciones.xyxy:
            ancho = max(1.0, x2 - x1)
            alto = max(1.0, y2 - y1)
            margen_x = ancho * self.margen_dinamico
            margen_y = alto * self.margen_dinamico
            izquierda = int(max(0, x1 - margen_x))
            arriba = int(max(0, y1 - margen_y))
            derecha = int(min(ancho_frame - 1, x2 + margen_x))
            abajo = int(min(alto_frame - 1, y2 + margen_y))
            poligonos.append(
                np.array(
                    [
                        [izquierda, arriba],
                        [derecha, arriba],
                        [derecha, abajo],
                        [izquierda, abajo],
                    ],
                    dtype=int,
                )
            )
        return poligonos

    @staticmethod
    def _crear_zonas(
        nombre: str, poligonos: list[np.ndarray], color: sv.Color
    ) -> list[ZonaAnotada]:
        zonas = []
        for poligono in poligonos:
            zona = sv.PolygonZone(
                polygon=poligono,
                triggering_anchors=(sv.Position.CENTER,),
            )
            anotador = sv.PolygonZoneAnnotator(
                zone=zona,
                color=color,
                thickness=2,
                text_scale=0.45,
                text_thickness=1,
                opacity=0.08,
            )
            zonas.append(ZonaAnotada(nombre, zona, anotador))
        return zonas

    def _actualizar_zonas_tipo(
        self,
        nombre: str,
        color_hex: str,
        especificacion: list[tuple[float, float]] | None,
        detecciones: sv.Detections,
        zonas_actuales: list[ZonaAnotada],
        ultimo_ts: float | None,
        resolucion: tuple[int, int],
        cambio_resolucion: bool,
        momento: float,
    ) -> tuple[list[ZonaAnotada], float | None]:
        if especificacion is not None:
            if cambio_resolucion or not zonas_actuales:
                poligono = self._escalar(especificacion, resolucion)
                return (
                    self._crear_zonas(
                        nombre, [poligono], sv.Color.from_hex(color_hex)
                    ),
                    ultimo_ts,
                )
            return zonas_actuales, ultimo_ts

        if not self.permitir_dinamicas:
            return [], None

        if len(detecciones):
            zonas = self._crear_zonas(
                nombre,
                self._desde_cajas(detecciones, resolucion),
                sv.Color.from_hex(color_hex),
            )
            return zonas, momento

        if (
            cambio_resolucion
            or ultimo_ts is None
            or (momento - ultimo_ts) > self.ttl_dinamico
        ):
            return [], None

        return zonas_actuales, ultimo_ts

    def actualizar(
        self,
        comederos: sv.Detections,
        bebederos: sv.Detections,
        forma_frame: tuple[int, ...],
        ahora: float | None = None,
    ) -> None:
        alto, ancho = forma_frame[:2]
        resolucion = (ancho, alto)
        cambio_resolucion = resolucion != self.resolucion
        self.resolucion = resolucion
        momento = time.monotonic() if ahora is None else float(ahora)

        self.zonas_comedero, self._ultimo_comedero_ts = self._actualizar_zonas_tipo(
            "Comedero",
            "#EF4444",
            self.especificacion_comedero,
            comederos,
            self.zonas_comedero,
            self._ultimo_comedero_ts,
            resolucion,
            cambio_resolucion,
            momento,
        )
        self.zonas_bebedero, self._ultimo_bebedero_ts = self._actualizar_zonas_tipo(
            "Bebedero",
            "#3B82F6",
            self.especificacion_bebedero,
            bebederos,
            self.zonas_bebedero,
            self._ultimo_bebedero_ts,
            resolucion,
            cambio_resolucion,
            momento,
        )

    @staticmethod
    def _puntos_en_poligono(puntos: np.ndarray, poligono: np.ndarray) -> np.ndarray:
        """Evalúa por ray-casting vectorial si cada punto (x, y) cae dentro del polígono."""
        if len(puntos) == 0 or len(poligono) < 3:
            return np.zeros(len(puntos), dtype=bool)
        px = puntos[:, 0:1]
        py = puntos[:, 1:2]
        poly = np.asarray(poligono, dtype=float)
        x1 = poly[:, 0]
        y1 = poly[:, 1]
        x2 = np.roll(x1, -1)
        y2 = np.roll(y1, -1)

        cruza_y = (y1 > py) != (y2 > py)
        dy = y2 - y1
        dy_seguro = np.where(dy != 0.0, dy, 1.0)
        inter_x = x1 + (py - y1) * (x2 - x1) / dy_seguro
        cruces = cruza_y & (px <= inter_x)
        dentro = (np.count_nonzero(cruces, axis=1) % 2) == 1

        dx_seg = x2 - x1
        dy_seg = y2 - y1
        largo2 = dx_seg * dx_seg + dy_seg * dy_seg
        en_borde = np.zeros(len(puntos), dtype=bool)
        for idx in range(len(poly)):
            if largo2[idx] <= 0.0:
                en_borde |= (px[:, 0] == x1[idx]) & (py[:, 0] == y1[idx])
                continue
            t = np.clip(
                ((px[:, 0] - x1[idx]) * dx_seg[idx] + (py[:, 0] - y1[idx]) * dy_seg[idx])
                / largo2[idx],
                0.0,
                1.0,
            )
            proy_x = x1[idx] + t * dx_seg[idx]
            proy_y = y1[idx] + t * dy_seg[idx]
            dist2 = (px[:, 0] - proy_x) ** 2 + (py[:, 0] - proy_y) ** 2
            en_borde |= dist2 <= 1e-6

        return dentro | en_borde

    @classmethod
    def _combinar_mascaras(
        cls, zonas: list[ZonaAnotada], aves: sv.Detections
    ) -> np.ndarray:
        mascara = np.zeros(len(aves), dtype=bool)
        if len(aves) == 0:
            for zona in zonas:
                zona.zona.trigger(aves)
            return mascara

        xyxy = np.asarray(aves.xyxy, dtype=float)
        x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]
        w = np.maximum(0.0, x2 - x1)
        h = np.maximum(0.0, y2 - y1)
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5
        anclas_anatomicas = (
            np.column_stack((cx, y1 + 0.2 * h)),
            np.column_stack((cx, y1 + 0.8 * h)),
            np.column_stack((x1 + 0.2 * w, cy)),
            np.column_stack((x1 + 0.8 * w, cy)),
        )

        for zona in zonas:
            en_zona = np.asarray(zona.zona.trigger(aves), dtype=bool)
            poligono = getattr(zona.zona, "polygon", None)
            if poligono is not None:
                for puntos in anclas_anatomicas:
                    en_zona |= cls._puntos_en_poligono(puntos, poligono)
                if hasattr(zona.zona, "current_count"):
                    zona.zona.current_count = int(np.count_nonzero(en_zona))
            mascara |= en_zona
        return mascara

    def evaluar(self, aves: sv.Detections) -> tuple[np.ndarray, np.ndarray]:
        return (
            self._combinar_mascaras(self.zonas_comedero, aves),
            self._combinar_mascaras(self.zonas_bebedero, aves),
        )

    def anotar(self, frame: np.ndarray) -> np.ndarray:
        for zona in self.zonas_comedero + self.zonas_bebedero:
            etiqueta = f"{zona.nombre}: {zona.zona.current_count}"
            frame = zona.anotador.annotate(scene=frame, label=etiqueta)
        return frame
