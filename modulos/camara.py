"""Captura de webcam o RTSP con frame reciente y reconexión automática."""

from __future__ import annotations

import os
import threading
import time

import cv2

try:
    import numpy as np
except ImportError:
    np = None


class CamaraStream:
    UMBRAL_CONGELADO_SEG = 30.0
    EPSILON_FRAME_CONGELADO = 1e-3

    def __init__(
        self,
        fuente: str | int,
        umbral_congelado_seg: float = UMBRAL_CONGELADO_SEG,
    ) -> None:
        self.fuente = fuente
        self.umbral_congelado_seg = float(umbral_congelado_seg)
        self.lock = threading.Lock()
        self.frame = None
        self.frame_id = 0
        self.running = False
        self.conectada = False
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ultimo_frame_ts = 0.0
        self.ultimo_error: str | None = None
        self.reintentos = 0
        self._capture = None
        self._frame_previo = None
        self._inicio_congelado_ts: float | None = None

    def start(self) -> None:
        if self.running:
            return
        if isinstance(self.fuente, str) and self.fuente.lower().startswith("rtsp://"):
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _marcar_desconectada(self, mensaje: str) -> None:
        with self.lock:
            cambio = mensaje != self.ultimo_error
            self.conectada = False
            self.frame = None
            self.ultimo_error = mensaje
            self.reintentos += 1
            self._frame_previo = None
            self._inicio_congelado_ts = None
        if cambio:
            print(f"Cámara no disponible: {mensaje}")

    def _detectar_frame_congelado(self, frame, ahora: float) -> bool:
        """Detecta si el stream entrega fotogramas idénticos durante más del umbral."""
        if np is None or frame is None:
            return False
        if (
            self._frame_previo is None
            or getattr(frame, "shape", None) != getattr(self._frame_previo, "shape", None)
        ):
            self._frame_previo = frame.copy()
            self._inicio_congelado_ts = ahora
            return False

        diferencia = float(
            np.mean(
                np.abs(
                    frame.astype(np.float32) - self._frame_previo.astype(np.float32)
                )
            )
        )
        if diferencia > self.EPSILON_FRAME_CONGELADO:
            self._frame_previo = frame.copy()
            self._inicio_congelado_ts = ahora
            return False

        if self._inicio_congelado_ts is None:
            self._inicio_congelado_ts = ahora
            return False

        return (ahora - self._inicio_congelado_ts) > self.umbral_congelado_seg

    def _marcar_conectada(self) -> None:
        with self.lock:
            reconectada = not self.conectada
            self.conectada = True
            self.ultimo_error = None
        if reconectada:
            print("Cámara conectada.")

    def _abrir_captura(self):
        if isinstance(self.fuente, str) and self.fuente.strip().lower().startswith(
            ("ventana:", "window:")
        ):
            from modulos.captura_ventana import CapturaVentana

            _, titulo = self.fuente.split(":", 1)
            return CapturaVentana(titulo.strip())

        if isinstance(self.fuente, int) and os.name == "nt" and hasattr(cv2, "CAP_DSHOW"):
            captura = cv2.VideoCapture(self.fuente, cv2.CAP_DSHOW)
            if not captura.isOpened():
                captura.release()
                captura = cv2.VideoCapture(self.fuente)
        else:
            captura = cv2.VideoCapture(self.fuente)

        try:
            captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if isinstance(self.fuente, int) and hasattr(cv2, "VideoWriter_fourcc"):
                captura.set(
                    cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")
                )
                captura.set(cv2.CAP_PROP_FPS, 60)
        except Exception:
            pass
        return captura

    def _loop(self) -> None:
        espera = 1.0
        while self.running:
            captura = self._abrir_captura()
            self._capture = captura

            if not captura.isOpened():
                self._marcar_desconectada("no fue posible abrir la fuente")
                captura.release()
                self._capture = None
                self.stop_event.wait(espera)
                espera = min(10.0, espera * 2.0)
                continue

            self._marcar_conectada()
            espera = 1.0
            while self.running:
                recibido, frame = captura.read()
                if not recibido or frame is None:
                    if self.running:
                        self._marcar_desconectada("se perdió la señal")
                    break
                ahora = time.monotonic()
                if self._detectar_frame_congelado(frame, ahora):
                    if self.running:
                        self._marcar_desconectada("imagen congelada")
                    break
                with self.lock:
                    self.frame = frame
                    self.frame_id += 1
                    self.ultimo_frame_ts = ahora

            captura.release()
            self._capture = None
            if self.running:
                self.stop_event.wait(espera)
                espera = min(10.0, espera * 2.0)

    def leer(self):
        with self.lock:
            if self.frame is None:
                return self.frame_id, None
            return self.frame_id, self.frame.copy()

    def estado(self) -> dict:
        with self.lock:
            antiguedad = (
                time.monotonic() - self.ultimo_frame_ts
                if self.ultimo_frame_ts
                else None
            )
            return {
                "conectada": self.conectada,
                "ultimo_error": self.ultimo_error,
                "reintentos": self.reintentos,
                "segundos_desde_frame": antiguedad,
            }

    def stop(self) -> None:
        self.running = False
        self.stop_event.set()
        captura = self._capture
        if captura is not None:
            try:
                captura.release()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
