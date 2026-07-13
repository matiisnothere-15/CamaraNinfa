"""Capa de postprocesamiento visual basada en Roboflow Supervision.

Convierte resultados Ultralytics a ``sv.Detections``, aplica los filtros de
clase/confianza, mantiene metadatos por ave y dibuja cajas, etiquetas, trazas y
zonas. El tracking continúa siendo responsabilidad de Ultralytics/BoT-SORT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

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
    """Adapta Ultralytics al formato común de Supervision."""

    def __init__(
        self,
        nombres_clases: dict[int, str] | list[str],
        confianza_ninfa: float,
        confianza_platos: float,
        area_minima: int,
        area_maxima: int,
    ) -> None:
        clases = _mapa_clases(nombres_clases)
        faltantes = {"ninfa", "comedero", "bebedero"} - clases.keys()
        if faltantes:
            raise ValueError(
                "El modelo no contiene las clases requeridas: "
                + ", ".join(sorted(faltantes))
            )

        self.id_ninfa = clases["ninfa"]
        self.id_comedero = clases["comedero"]
        self.id_bebedero = clases["bebedero"]
        self.confianza_ninfa = confianza_ninfa
        self.confianza_platos = confianza_platos
        self.area_minima = area_minima
        self.area_maxima = area_maxima

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

        es_ninfa = clases == self.id_ninfa
        es_comedero = clases == self.id_comedero
        es_bebedero = clases == self.id_bebedero
        confianza_valida = (es_ninfa & (confianzas >= self.confianza_ninfa)) | (
            (es_comedero | es_bebedero) & (confianzas >= self.confianza_platos)
        )
        mascara = (
            (areas >= self.area_minima)
            & (areas <= self.area_maxima)
            & confianza_valida
        )
        detecciones = detecciones[mascara]

        if len(detecciones) == 0:
            vacias = detecciones[np.zeros(0, dtype=bool)]
            return ResultadoVision(vacias, vacias, vacias, vacias, [], [])

        clases = detecciones.class_id.astype(int)
        confianzas = detecciones.confidence
        if confianzas is None:
            confianzas = np.ones(len(detecciones), dtype=float)

        mascara_aves = clases == self.id_ninfa
        mascara_comederos = clases == self.id_comedero
        mascara_bebederos = clases == self.id_bebedero
        tracker_ids = detecciones.tracker_id

        alto_frame, ancho_frame = frame.shape[:2]
        datos_aves = {}
        tracks_visibles = []
        for indice in np.flatnonzero(mascara_aves):
            indice = int(indice)
            confianza = float(confianzas[indice])
            track_id = int(tracker_ids[indice]) if tracker_ids is not None else None
            coords = tuple(detecciones.xyxy[indice].astype(int).tolist())
            datos_aves[indice] = (coords, confianza, track_id)
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
            identificador.votar(track_id, frame, coords)
            tracks_visibles.append(track_id)

        identidades = identificador.resolver(tracks_visibles)
        etiquetas = []
        aves_info = []
        for indice in range(len(detecciones)):
            clase_id = int(clases[indice])
            confianza = float(confianzas[indice])

            if clase_id == self.id_ninfa:
                coords, confianza, track_id = datos_aves[indice]
                ave_id, nombre_ave = identidades.get(track_id, (None, None))

                etiqueta = nombre_ave or "ninfa"
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
    """Compone los anotadores oficiales de Supervision."""

    def __init__(self) -> None:
        self.cajas = sv.BoxAnnotator(thickness=2)
        self.etiquetas = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
        self.trazas = sv.TraceAnnotator(thickness=2, trace_length=30)

    def anotar(self, frame: np.ndarray, resultado: ResultadoVision) -> np.ndarray:
        if len(resultado.detecciones) == 0:
            return frame

        if len(resultado.aves) and resultado.aves.tracker_id is not None:
            frame = self.trazas.annotate(scene=frame, detections=resultado.aves)
        frame = self.cajas.annotate(scene=frame, detections=resultado.detecciones)
        return self.etiquetas.annotate(
            scene=frame,
            detections=resultado.detecciones,
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

    def __init__(self, margen_dinamico: float = 0.20) -> None:
        self.margen_dinamico = max(0.0, margen_dinamico)
        self.especificacion_comedero = self._leer_zona("ZONA_COMEDERO")
        self.especificacion_bebedero = self._leer_zona("ZONA_BEBEDERO")
        self.resolucion: tuple[int, int] | None = None
        self.zonas_comedero: list[ZonaAnotada] = []
        self.zonas_bebedero: list[ZonaAnotada] = []

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

    def actualizar(
        self,
        comederos: sv.Detections,
        bebederos: sv.Detections,
        forma_frame: tuple[int, ...],
    ) -> None:
        alto, ancho = forma_frame[:2]
        resolucion = (ancho, alto)
        cambio_resolucion = resolucion != self.resolucion
        self.resolucion = resolucion

        if self.especificacion_comedero is not None:
            if cambio_resolucion or not self.zonas_comedero:
                poligono = self._escalar(self.especificacion_comedero, resolucion)
                self.zonas_comedero = self._crear_zonas(
                    "Comedero", [poligono], sv.Color.from_hex("#EF4444")
                )
        elif len(comederos):
            self.zonas_comedero = self._crear_zonas(
                "Comedero",
                self._desde_cajas(comederos, resolucion),
                sv.Color.from_hex("#EF4444"),
            )

        if self.especificacion_bebedero is not None:
            if cambio_resolucion or not self.zonas_bebedero:
                poligono = self._escalar(self.especificacion_bebedero, resolucion)
                self.zonas_bebedero = self._crear_zonas(
                    "Bebedero", [poligono], sv.Color.from_hex("#3B82F6")
                )
        elif len(bebederos):
            self.zonas_bebedero = self._crear_zonas(
                "Bebedero",
                self._desde_cajas(bebederos, resolucion),
                sv.Color.from_hex("#3B82F6"),
            )

    @staticmethod
    def _combinar_mascaras(
        zonas: list[ZonaAnotada], aves: sv.Detections
    ) -> np.ndarray:
        mascara = np.zeros(len(aves), dtype=bool)
        for zona in zonas:
            mascara |= zona.zona.trigger(aves)
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
