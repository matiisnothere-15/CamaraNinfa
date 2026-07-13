"""Monitoreo de audio RTSP con estado de conexión y FFT segura."""

from __future__ import annotations

import threading
import time

import av
import numpy as np


class AudioMonitorNulo:
    """Interfaz de audio cuando la fuente seleccionada no lo proporciona."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def get_status(self) -> dict:
        return {
            "status": "Sin audio",
            "rms": 0.0,
            "freq": 0.0,
            "disponible": False,
            "error": None,
            "reintentos": 0,
        }


class AudioMonitor:
    SAMPLE_RATE = 16_000
    RMS_THRESHOLD_SCREAM = 0.20
    RMS_THRESHOLD_CONTENT = 0.02
    FREQ_THRESHOLD_HIGH = 1_500.0
    MAX_SIN_DATOS = 10.0

    def __init__(self, rtsp_url: str) -> None:
        self.url = rtsp_url
        self.running = False
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.latest_status = "Sin audio"
        self.latest_rms = 0.0
        self.latest_freq = 0.0
        self.latest_update = 0.0
        self.connected = False
        self.last_error: str | None = None
        self.reintentos = 0
        self.lock = threading.Lock()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.running = False
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def _marcar_error(self, error: Exception | str) -> None:
        mensaje = str(error)
        with self.lock:
            cambio = mensaje != self.last_error
            self.connected = False
            self.latest_status = "Sin audio"
            self.latest_rms = 0.0
            self.latest_freq = 0.0
            self.last_error = mensaje
            self.reintentos += 1
        if cambio:
            print(f"Audio no disponible: {mensaje}")

    def get_status(self) -> dict:
        ahora = time.monotonic()
        with self.lock:
            sin_datos = bool(
                self.latest_update and (ahora - self.latest_update) > self.MAX_SIN_DATOS
            )
            disponible = self.connected and not sin_datos
            error = self.last_error
            if sin_datos and not error:
                error = "Audio sin datos recientes"
            return {
                "status": self.latest_status if disponible else "Sin audio",
                "rms": self.latest_rms if disponible else 0.0,
                "freq": self.latest_freq if disponible else 0.0,
                "disponible": disponible,
                "error": error,
                "reintentos": self.reintentos,
            }

    def _monitor_loop(self) -> None:
        print("Iniciando monitoreo de audio...")
        while self.running:
            container = None
            try:
                container = av.open(
                    self.url,
                    options={"rtsp_transport": "tcp", "stimeout": "5000000"},
                )
                if not container.streams.audio:
                    raise RuntimeError("La cámara no publica un stream de audio")

                stream = container.streams.audio[0]
                resampler = av.AudioResampler(
                    format="flt",
                    layout="mono",
                    rate=self.SAMPLE_RATE,
                )

                for frame in container.decode(stream):
                    if not self.running:
                        break
                    salidas = resampler.resample(frame)
                    if salidas is None:
                        continue
                    if not isinstance(salidas, (list, tuple)):
                        salidas = [salidas]
                    for salida in salidas:
                        self._analyze_chunk(salida.to_ndarray())

                if self.running:
                    raise RuntimeError("El stream de audio terminó inesperadamente")
            except Exception as error:
                if self.running:
                    self._marcar_error(error)
                    self.stop_event.wait(5.0)
            finally:
                if container is not None:
                    try:
                        container.close()
                    except Exception:
                        pass

    def _analyze_chunk(self, data) -> None:
        muestras = np.asarray(data, dtype=np.float32).reshape(-1)
        if muestras.size < 2:
            return

        rms = float(np.sqrt(np.mean(np.square(muestras))))
        frecuencia = 0.0
        if rms > 0.001:
            centradas = muestras - float(np.mean(muestras))
            ventana = np.hanning(centradas.size)
            espectro = np.abs(np.fft.rfft(centradas * ventana))
            frecuencias = np.fft.rfftfreq(centradas.size, d=1.0 / self.SAMPLE_RATE)
            if espectro.size:
                espectro[0] = 0.0
                frecuencia = float(frecuencias[int(np.argmax(espectro))])

        if rms > self.RMS_THRESHOLD_SCREAM:
            estado = (
                "Gritando"
                if frecuencia > self.FREQ_THRESHOLD_HIGH
                else "Ruido Fuerte"
            )
        elif rms > self.RMS_THRESHOLD_CONTENT:
            estado = "Sonidos"
        else:
            estado = "Silencio"

        with self.lock:
            self.latest_rms = rms
            self.latest_freq = frecuencia
            self.latest_status = estado
            self.latest_update = time.monotonic()
            self.connected = True
            self.last_error = None
