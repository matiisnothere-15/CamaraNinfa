"""Captura de webcam o RTSP con frame reciente y reconexión automática."""

from __future__ import annotations

import os
import threading
import time

import cv2


class CamaraStream:
    def __init__(self, fuente: str | int) -> None:
        self.fuente = fuente
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
        if cambio:
            print(f"Cámara no disponible: {mensaje}")

    def _marcar_conectada(self) -> None:
        with self.lock:
            reconectada = not self.conectada
            self.conectada = True
            self.ultimo_error = None
        if reconectada:
            print("Cámara conectada.")

    def _loop(self) -> None:
        espera = 1.0
        while self.running:
            captura = cv2.VideoCapture(self.fuente)
            self._capture = captura
            try:
                captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

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
                if not recibido:
                    if self.running:
                        self._marcar_desconectada("se perdió la señal")
                    break
                ahora = time.monotonic()
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
