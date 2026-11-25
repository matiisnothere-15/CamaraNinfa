"""Identificación exclusiva de ninfas por color de plumaje y track."""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict, deque

import cv2
import numpy as np

PATRONES_TIPO = [
    ("amarilla", r"lutino"),
    ("blanca", r"albino"),
    ("gris", r"gris|plomo|silvestre|platead|oscur"),
    ("amarilla", r"amarill"),
    ("blanca", r"blanc"),
]

FRAC_AMARILLO = 0.22
FRAC_BLANCO = 0.45
FRAC_ACROMATICO = 0.45
MAX_AMARILLO_EN_GRIS = 0.08
FRAC_AMARILLO_CABEZA = 0.08
VALOR_GRIS_MAXIMO = 145
MIN_VOTOS = 8
MAYORIA = 0.70
SAT_FRAME_MINIMA = 12.0
MAX_EDAD_TRACK = 120.0


class IdentificadorColor:
    """Asigna como máximo un track activo a cada ave registrada.

    Los votos de color estabilizan la clasificación. ``resolver`` considera
    todos los tracks visibles a la vez, de modo que dos cajas no puedan recibir
    simultáneamente el nombre de Mushu o Yukki.
    """

    def __init__(self, historial: int = 60) -> None:
        self.historial = historial
        self.tipo_a_ave: dict[str, dict] = {}
        self.votos: dict[int, deque] = {}
        self.ultima_vez: dict[int, float] = {}
        self.color_disponible: dict[int, bool] = {}
        self.asignaciones: dict[int, tuple[int | None, str]] = {}
        self.activo = False

    @staticmethod
    def _construir_mapa_aves(aves: list[dict]) -> dict[str, dict]:
        mapa: dict[str, dict] = {}
        for ave in aves:
            # El color corporal manda sobre notas como "cara amarilla".
            # Elegir antes de deduplicar evita inventar otro tipo si está ocupado.
            coincidencias = (
                tipo
                for campo in ("color", "notas")
                for tipo, patron in PATRONES_TIPO
                if re.search(patron, (ave.get(campo) or "").lower())
            )
            tipo = next(coincidencias, None)
            if tipo is not None and tipo not in mapa:
                mapa[tipo] = {"id": ave.get("id"), "nombre": ave["nombre"]}
        return mapa

    def configurar(self, aves: list[dict]) -> bool:
        self.tipo_a_ave = self._construir_mapa_aves(aves)
        self.votos.clear()
        self.ultima_vez.clear()
        self.color_disponible.clear()
        self.asignaciones.clear()
        self.activo = len(self.tipo_a_ave) >= 2
        return self.activo

    def sincronizar_aves(self, aves: list[dict]) -> bool:
        """Actualiza aves en caliente sin borrar los votos HSV acumulados."""
        nuevo_mapa = self._construir_mapa_aves(aves)
        if len(nuevo_mapa) < 2 or nuevo_mapa == self.tipo_a_ave:
            return False
        self.tipo_a_ave = nuevo_mapa
        self.activo = True
        self.asignaciones.clear()
        return True

    @staticmethod
    def frame_tiene_color(frame: np.ndarray) -> bool:
        if frame is None or frame.size == 0:
            return False
        muestra = frame[::8, ::8]
        hsv = cv2.cvtColor(muestra, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[:, :, 1])) >= SAT_FRAME_MINIMA

    @staticmethod
    def clasificar_color(
        frame: np.ndarray, coords: tuple[int, int, int, int]
    ) -> str | None:
        x1, y1, x2, y2 = coords
        alto_frame, ancho_frame = frame.shape[:2]
        x1 = max(0, min(ancho_frame, x1))
        x2 = max(0, min(ancho_frame, x2))
        y1 = max(0, min(alto_frame, y1))
        y2 = max(0, min(alto_frame, y2))
        if x2 <= x1 or y2 <= y1:
            return None

        margen_x = (x2 - x1) // 4
        margen_y = (y2 - y1) // 4
        recorte = frame[y1 + margen_y : y2 - margen_y, x1 + margen_x : x2 - margen_x]
        if recorte.size == 0:
            return None

        hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        validos = v > 40
        total = int(np.count_nonzero(validos))
        if total < 50:
            return None

        amarillo = np.count_nonzero(
            validos & (h >= 15) & (h <= 40) & (s > 70) & (v > 100)
        ) / total
        blanco = np.count_nonzero(validos & (s < 45) & (v > 185)) / total
        gris = np.count_nonzero(validos & (s < 55) & (v <= VALOR_GRIS_MAXIMO)) / total
        gris_medio = np.count_nonzero(
            validos & (s >= 18) & (s < 55) & (v <= 185)
        ) / total
        amarillo_suave_cuerpo = np.count_nonzero(
            validos & (h >= 15) & (h <= 40) & (s >= 20) & (v > 80)
        ) / total

        if amarillo >= FRAC_AMARILLO:
            if gris >= 0.35:
                return None  # Caja fusionada con evidencia de ambos plumajes.
            return "amarilla"

        # El centro de un lutino a contraluz puede verse gris y excluir la cara.
        # Muestrear también la parte superior permite ver amarillo poco saturado,
        # sin asumir que toda ave con cara amarilla tiene cuerpo lutino.
        ancho, alto = x2 - x1, y2 - y1
        cabeza = frame[
            y1 + int(alto * 0.03) : y1 + int(alto * 0.40),
            x1 + int(ancho * 0.08) : x2 - int(ancho * 0.08),
        ]
        cabeza_amarilla = False
        if cabeza.size:
            hsv_cabeza = cv2.cvtColor(cabeza, cv2.COLOR_BGR2HSV)
            hc, sc, vc = (hsv_cabeza[:, :, i] for i in range(3))
            total_cabeza = int(np.count_nonzero(vc > 40))
            if total_cabeza >= 50:
                calidos = (hc >= 15) & (hc <= 40) & (vc > 80)
                suave = np.count_nonzero(calidos & (sc >= 20)) / total_cabeza
                marcado = np.count_nonzero(calidos & (sc >= 35)) / total_cabeza
                cabeza_amarilla = (
                    suave >= FRAC_AMARILLO_CABEZA
                    and marcado >= 0.05
                    and suave - amarillo_suave_cuerpo >= 0.05
                )
        if cabeza_amarilla:
            cuerpo_claro = np.count_nonzero(validos & (v > VALOR_GRIS_MAXIMO)) / total
            if cuerpo_claro >= 0.65 and gris <= 0.25:
                return "amarilla"
            # Cara amarilla con cuerpo oscuro puede ser gris o lutino en sombra.
            # No convertir esa ambigüedad en una identidad individual.
            return None

        if blanco >= FRAC_BLANCO and amarillo <= MAX_AMARILLO_EN_GRIS:
            return "blanca"
        if (
            max(gris, gris_medio) >= FRAC_ACROMATICO
            and amarillo <= MAX_AMARILLO_EN_GRIS
        ):
            return "gris"
        return None

    def registrar_voto(self, track_id: int, tipo: str, ahora: float | None = None) -> None:
        """Registra un voto ya clasificado; también facilita pruebas deterministas."""
        if not self.activo or tipo not in self.tipo_a_ave:
            return
        ahora = time.monotonic() if ahora is None else ahora
        votos = self.votos.setdefault(track_id, deque(maxlen=self.historial))
        votos.append(tipo)
        self.ultima_vez[track_id] = ahora
        self.color_disponible[track_id] = True

    def suspender(self, track_id: int, ahora: float | None = None) -> None:
        """Retira el nombre y exige votos nuevos después de mezcla u oclusión."""
        if track_id is None:
            return
        self.votos.pop(track_id, None)
        self.asignaciones.pop(track_id, None)
        self.color_disponible[track_id] = False
        self.ultima_vez[track_id] = time.monotonic() if ahora is None else ahora

    def votar(
        self,
        track_id: int,
        frame: np.ndarray,
        coords: tuple[int, int, int, int],
        ahora: float | None = None,
    ) -> str | None:
        if not self.activo or track_id is None:
            return None
        ahora = time.monotonic() if ahora is None else ahora
        self.limpiar(ahora)
        self.ultima_vez[track_id] = ahora

        if not self.frame_tiene_color(frame):
            self.suspender(track_id, ahora)
            return None

        tipo = self.clasificar_color(frame, coords)
        if tipo not in self.tipo_a_ave:
            self.suspender(track_id, ahora)
            return tipo
        votos = self.votos.get(track_id)
        if votos and votos[-1] != tipo:
            # Un ID del tracker puede pasar de un ave a otra al cruzarse.
            self.suspender(track_id, ahora)
        self.registrar_voto(track_id, tipo, ahora)
        return tipo

    def _candidatura(self, track_id: int):
        votos = self.votos.get(track_id)
        if (
            not votos
            or len(votos) < MIN_VOTOS
            or not self.color_disponible.get(track_id, False)
        ):
            return None
        tipo, cantidad = Counter(votos).most_common(1)[0]
        proporcion = cantidad / len(votos)
        if proporcion < MAYORIA or tipo not in self.tipo_a_ave:
            return None
        puntuacion = (
            proporcion,
            cantidad,
            self.ultima_vez.get(track_id, 0.0),
            -track_id,
        )
        return tipo, puntuacion

    def limpiar(self, ahora: float | None = None) -> None:
        ahora = time.monotonic() if ahora is None else ahora
        antiguos = [
            track_id
            for track_id, ultima in self.ultima_vez.items()
            if (ahora - ultima) > MAX_EDAD_TRACK
        ]
        for track_id in antiguos:
            self.votos.pop(track_id, None)
            self.ultima_vez.pop(track_id, None)
            self.color_disponible.pop(track_id, None)
            self.asignaciones.pop(track_id, None)

    def resolver(
        self, track_ids: list[int] | None = None, ahora: float | None = None
    ) -> dict[int, tuple[int | None, str]]:
        """Resuelve identidades de forma conjunta y exclusiva."""
        ahora = time.monotonic() if ahora is None else ahora
        self.limpiar(ahora)
        activos = set(self.votos) if track_ids is None else set(track_ids)
        por_tipo = defaultdict(list)

        for track_id in activos:
            candidatura = self._candidatura(track_id)
            if candidatura is not None:
                tipo, puntuacion = candidatura
                por_tipo[tipo].append((puntuacion, track_id))

        asignaciones = {}
        for tipo, candidatos in por_tipo.items():
            _puntuacion, ganador = max(candidatos)
            ave = self.tipo_a_ave[tipo]
            asignaciones[ganador] = (ave["id"], ave["nombre"])

        self.asignaciones = asignaciones
        return dict(asignaciones)

    def identificar(self, track_id: int) -> tuple[int | None, str | None]:
        return self.asignaciones.get(track_id, (None, None))
