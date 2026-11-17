"""Recolección activa (Active Learning) de fotogramas dudosos para mejorar el dataset.

Cuando ``NINFAS_AUTO_DATASET=1``, guarda en disco fotogramas crudos (sin cajas
dibujadas) donde el modelo presenta baja confianza o no logra detectar el
comedero pese a haber aves visibles, respetando un enfriamiento (cooldown) y un
límite máximo de archivos.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


def _auto_dataset_habilitado() -> bool:
    return os.getenv("NINFAS_AUTO_DATASET", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "si",
    }


def _evidencia_eventos_habilitada() -> bool:
    return os.getenv("NINFAS_EVIDENCIA_EVENTOS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


class RecolectorActivoDataset:
    """Guarda fotogramas candidatos para reentrenamiento con control de cuota."""

    def __init__(
        self,
        directorio: str | Path | None = None,
        habilitado: bool | None = None,
        intervalo_minimo_segundos: float = 900.0,
        max_archivos: int = 200,
        conf_duda_max: float = 0.48,
        escritor_imagen: Callable[[Path, np.ndarray], bool] | None = None,
        asincrono: bool | None = None,
        max_frames_buffer: int = 30,
        evidencia_habilitada: bool | None = None,
    ) -> None:
        raiz = Path(__file__).resolve().parent.parent
        self.directorio = (
            Path(directorio)
            if directorio is not None
            else raiz / "dataset" / "capturas_activas"
        )
        self.habilitado = (
            _auto_dataset_habilitado() if habilitado is None else bool(habilitado)
        )
        if evidencia_habilitada is None:
            self.evidencia_habilitada = (
                False
                if habilitado is False
                else bool(self.habilitado or _evidencia_eventos_habilitada())
            )
        else:
            self.evidencia_habilitada = bool(evidencia_habilitada)
        self.intervalo_minimo_segundos = max(10.0, float(intervalo_minimo_segundos))
        self.max_archivos = max(1, int(max_archivos))
        self.conf_duda_max = float(conf_duda_max)
        self._escritor_imagen = escritor_imagen or self._guardar_jpg
        self.asincrono = (
            (escritor_imagen is None) if asincrono is None else bool(asincrono)
        )
        self._ultima_captura: float | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._archivos_en_vuelo: int = 0
        self._secuencia_evidencia: int = 0
        self._lock = threading.Lock()
        self._buffer_frames: deque[tuple[float, np.ndarray]] = deque(
            maxlen=max(1, int(max_frames_buffer))
        )

    @staticmethod
    def _guardar_jpg(ruta: Path, frame: np.ndarray) -> bool:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        return bool(
            cv2.imwrite(str(ruta), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        )

    def _contar_existentes(self) -> int:
        if not self.directorio.is_dir():
            return 0
        return sum(1 for _ in self.directorio.glob("*.jpg"))

    @staticmethod
    def _extraer_confianzas_crudas(resultados_crudos) -> np.ndarray | None:
        if resultados_crudos is None:
            return None
        primero = resultados_crudos
        if not hasattr(primero, "boxes"):
            try:
                primero = resultados_crudos[0]
            except (IndexError, KeyError, TypeError):
                return None
        boxes = getattr(primero, "boxes", None)
        conf = getattr(boxes, "conf", None)
        if conf is None:
            return None
        if hasattr(conf, "detach"):
            conf = conf.detach()
        if hasattr(conf, "cpu"):
            conf = conf.cpu()
        if hasattr(conf, "numpy"):
            conf = conf.numpy()
        valores = np.asarray(conf, dtype=float).ravel()
        return valores if len(valores) > 0 else None

    def motivo_captura(
        self, resultado_vision, resultados_crudos=None
    ) -> str | None:
        """Determina si el frame aporta valor de entrenamiento (Active Learning)."""
        if resultado_vision is None:
            return None

        # Caso 1: Hay aves detectadas pero el comedero no fue detectado (brecha recall comedero)
        if len(resultado_vision.aves) > 0 and len(resultado_vision.comederos) == 0:
            return "comedero_no_detectado"

        # Caso 2: Alguna detección cruda (antes del filtro >= 0.55) cayó en duda
        confianzas = self._extraer_confianzas_crudas(resultados_crudos)
        if confianzas is None:
            confianzas = getattr(resultado_vision.detecciones, "confidence", None)
        if confianzas is not None and len(confianzas) > 0:
            min_conf = float(np.min(confianzas))
            if min_conf <= self.conf_duda_max:
                return f"baja_confianza_{int(round(min_conf * 100)):02d}"

        return None

    def _rotar_existentes(self, maximo_objetivo: int) -> None:
        if not self.directorio.is_dir():
            return
        con_orden: list[tuple[int, str, Path]] = []
        for archivo in self.directorio.glob("*.jpg"):
            try:
                con_orden.append((archivo.stat().st_mtime_ns, archivo.name, archivo))
            except OSError:
                continue
        con_orden.sort(key=lambda item: (item[0], item[1]))
        excedente = len(con_orden) - max(0, maximo_objetivo)
        if excedente <= 0:
            return
        for _mtime, _nombre, archivo in con_orden[:excedente]:
            try:
                archivo.unlink(missing_ok=True)
            except OSError:
                pass

    def _guardar_en_segundo_plano(
        self, ruta: Path, copia: np.ndarray, rotar_antiguos: bool = False
    ) -> None:
        try:
            if rotar_antiguos:
                with self._lock:
                    self._rotar_existentes(max(0, self.max_archivos - 1))
            self._escritor_imagen(ruta, copia)
        except Exception as error:
            print(f"No se pudo guardar captura activa {ruta.name}: {error}")
        finally:
            with self._lock:
                self._archivos_en_vuelo = max(0, self._archivos_en_vuelo - 1)

    def _despachar_escritura_bloqueada(
        self, ruta: Path, copia: np.ndarray, rotar_antiguos: bool = False
    ) -> bool:
        if (self._contar_existentes() + self._archivos_en_vuelo) >= self.max_archivos:
            if not rotar_antiguos:
                return False
            self._rotar_existentes(
                max(0, self.max_archivos - 1 - self._archivos_en_vuelo)
            )
        if not self.asincrono:
            return bool(self._escritor_imagen(ruta, copia))
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="captura-activa"
            )
        self._archivos_en_vuelo += 1
        self._executor.submit(
            self._guardar_en_segundo_plano, ruta, copia, rotar_antiguos
        )
        return True

    def registrar_frame(
        self, frame: np.ndarray, timestamp: float | None = None
    ) -> None:
        """Conserva en un buffer circular los fotogramas recientes para evidencia de eventos."""
        if frame is None:
            return
        instante = time.monotonic() if timestamp is None else float(timestamp)
        with self._lock:
            self._buffer_frames.append((instante, frame.copy()))

    def guardar_evidencia_evento(
        self,
        evento_estado: str,
        tipo_evento: str,
        track_id: int,
        nombre_ave: str | None = None,
        ahora: float | None = None,
    ) -> Path | None:
        """Guarda evidencia visual del evento usando el frame más cercano en el buffer."""
        del tipo_evento
        if not self.evidencia_habilitada:
            return None

        instante = time.monotonic() if ahora is None else float(ahora)
        estado_tag = (
            re.sub(r"[^a-zA-Z0-9_-]+", "_", str(evento_estado)).strip("_").lower()
            or "evento"
        )
        ave_base = nombre_ave if nombre_ave else f"track_{track_id}"
        ave_tag = (
            re.sub(r"[^a-zA-Z0-9_-]+", "_", str(ave_base)).strip("_")
            or f"track_{track_id}"
        )

        with self._lock:
            if not self._buffer_frames:
                return None
            self._secuencia_evidencia += 1
            sello = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            ruta = (
                self.directorio
                / f"evidencia_{sello}_{self._secuencia_evidencia:04d}_{estado_tag}_{ave_tag}.jpg"
            )
            _, frame_elegido = min(
                self._buffer_frames, key=lambda item: abs(item[0] - instante)
            )
            if self._despachar_escritura_bloqueada(
                ruta, frame_elegido.copy(), rotar_antiguos=True
            ):
                return ruta
            return None

    def evaluar_y_guardar(
        self,
        frame: np.ndarray,
        resultado_vision,
        ahora: float | None = None,
        resultados_crudos=None,
    ) -> Path | None:
        """Si corresponde, guarda una copia limpia del frame y devuelve su ruta."""
        if not self.habilitado or frame is None:
            return None

        instante = time.monotonic() if ahora is None else ahora
        if (
            self._ultima_captura is not None
            and (instante - self._ultima_captura) < self.intervalo_minimo_segundos
        ):
            return None

        motivo = self.motivo_captura(
            resultado_vision, resultados_crudos=resultados_crudos
        )
        if motivo is None:
            return None

        sello = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        ruta = self.directorio / f"active_{sello}_{motivo}.jpg"
        copia = frame.copy()
        with self._lock:
            if self._despachar_escritura_bloqueada(ruta, copia):
                self._ultima_captura = instante
                return ruta
            return None

    def stop(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=True)
