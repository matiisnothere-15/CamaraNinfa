import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent


def cargar_audio_sin_pyav():
    ruta = RAIZ / "modulos/audio_analysis.py"
    nombre = "audio_analysis_test_module"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    av_falso = types.ModuleType("av")
    with patch.dict(sys.modules, {"av": av_falso, nombre: modulo}):
        spec.loader.exec_module(modulo)
    return modulo


class AudioMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_audio_sin_pyav()

    def test_audio_mono_bidimensional_se_aplana(self):
        monitor = self.modulo.AudioMonitor("rtsp://ejemplo")
        tiempo = np.arange(1600) / monitor.SAMPLE_RATE
        senal = (0.5 * np.sin(2 * np.pi * 2000 * tiempo)).reshape(1, -1)
        monitor._analyze_chunk(senal)
        estado = monitor.get_status()
        self.assertTrue(estado["disponible"])
        self.assertEqual("Gritando", estado["status"])
        self.assertAlmostEqual(2000.0, estado["freq"], delta=20.0)

    def test_silencio_publica_ceros_sin_error(self):
        monitor = self.modulo.AudioMonitor("rtsp://ejemplo")
        monitor._analyze_chunk(np.zeros((1, 800), dtype=np.float32))
        estado = monitor.get_status()
        self.assertEqual("Silencio", estado["status"])
        self.assertEqual(0.0, estado["freq"])

    def test_error_de_stream_es_visible(self):
        monitor = self.modulo.AudioMonitor("rtsp://ejemplo")
        monitor._marcar_error("sin conexión")
        estado = monitor.get_status()
        self.assertFalse(estado["disponible"])
        self.assertEqual("sin conexión", estado["error"])
        self.assertEqual(1, estado["reintentos"])


if __name__ == "__main__":
    unittest.main()
