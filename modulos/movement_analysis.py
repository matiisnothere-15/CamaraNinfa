"""Actividad por track normalizada por resolución y tiempo."""

from __future__ import annotations

import math
import time
from collections import deque


class MovementMonitor:
    """Mide desplazamiento como porcentaje de la diagonal del frame por minuto."""

    def __init__(
        self,
        history_seconds: float = 60.0,
        stale_track_seconds: float = 5.0,
        min_observation_seconds: float = 3.0,
        smoothing_alpha: float = 0.35,
    ) -> None:
        self.history_seconds = history_seconds
        self.stale_track_seconds = stale_track_seconds
        self.min_observation_seconds = min_observation_seconds
        self.smoothing_alpha = smoothing_alpha
        self.tracks: dict[int, deque] = {}
        self.smoothed_centers: dict[int, tuple[float, float]] = {}

        # Unidad: porcentaje de la diagonal del frame por minuto.
        self.HIGH_ACTIVITY_THRESHOLD = 50.0
        self.LOW_ACTIVITY_THRESHOLD = 5.0
        self.JITTER_THRESHOLD = 0.002

    def update(
        self,
        track_id: int,
        center_x: float,
        center_y: float,
        frame_width: int,
        frame_height: int,
        now: float | None = None,
    ) -> None:
        if frame_width <= 0 or frame_height <= 0:
            return
        now = time.monotonic() if now is None else now
        self._cleanup_old_tracks(now)

        normalizado = (center_x / frame_width, center_y / frame_height)
        anterior = self.smoothed_centers.get(track_id)
        if anterior is None:
            suavizado = normalizado
        else:
            alfa = self.smoothing_alpha
            suavizado = (
                alfa * normalizado[0] + (1.0 - alfa) * anterior[0],
                alfa * normalizado[1] + (1.0 - alfa) * anterior[1],
            )
        self.smoothed_centers[track_id] = suavizado
        self.tracks.setdefault(track_id, deque()).append((now, *suavizado))

    def _cleanup_old_tracks(self, now: float) -> None:
        limite_historial = now - self.history_seconds
        for track_id in list(self.tracks):
            puntos = self.tracks[track_id]
            while puntos and puntos[0][0] < limite_historial:
                puntos.popleft()
            if not puntos or (now - puntos[-1][0]) > self.stale_track_seconds:
                self.tracks.pop(track_id, None)
                self.smoothed_centers.pop(track_id, None)

    def _valor_actividad(self, track_id: int) -> float | None:
        puntos = self.tracks.get(track_id)
        if not puntos or len(puntos) < 2:
            return None
        duracion = puntos[-1][0] - puntos[0][0]
        if duracion < self.min_observation_seconds:
            return None

        distancia = 0.0
        for indice in range(1, len(puntos)):
            _, x1, y1 = puntos[indice - 1]
            _, x2, y2 = puntos[indice]
            paso = math.hypot(x2 - x1, y2 - y1) / math.sqrt(2.0)
            if paso >= self.JITTER_THRESHOLD:
                distancia += paso

        return distancia / duracion * 60.0 * 100.0

    def get_activity_level(
        self, track_id: int, now: float | None = None
    ) -> tuple[str, float]:
        now = time.monotonic() if now is None else now
        self._cleanup_old_tracks(now)
        valor = self._valor_actividad(track_id)
        if valor is None:
            return "Desconocido", 0.0
        if valor > self.HIGH_ACTIVITY_THRESHOLD:
            return "Muy Activo", valor
        if valor > self.LOW_ACTIVITY_THRESHOLD:
            return "Normal", valor
        return "Sedentario", valor

    def get_global_activity(self, now: float | None = None) -> tuple[str, float]:
        now = time.monotonic() if now is None else now
        self._cleanup_old_tracks(now)
        if not self.tracks:
            return "Sin datos", 0.0

        resultados = [
            (track_id, self._valor_actividad(track_id)) for track_id in self.tracks
        ]
        valores = [valor for _track_id, valor in resultados if valor is not None]
        if not valores:
            return "Sin datos", 0.0

        maximo = max(valores)
        if maximo > self.HIGH_ACTIVITY_THRESHOLD:
            return "Alta Actividad", maximo
        if maximo > self.LOW_ACTIVITY_THRESHOLD:
            return "Actividad Normal", maximo
        return "Tranquilo", maximo
