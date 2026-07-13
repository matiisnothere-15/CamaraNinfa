import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_camara_sin_opencv():
    ruta = RAIZ / "modulos/camara.py"
    nombre = "camara_test_module"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    cv2_falso = types.ModuleType("cv2")
    with patch.dict(sys.modules, {"cv2": cv2_falso, nombre: modulo}):
        spec.loader.exec_module(modulo)
    return modulo


class CamaraEstadoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_camara_sin_opencv()

    def test_estado_inicial_es_desconectado(self):
        camara = self.modulo.CamaraStream(0)
        estado = camara.estado()
        self.assertFalse(estado["conectada"])
        self.assertEqual(0, estado["reintentos"])
        self.assertEqual((0, None), camara.leer())

    def test_error_se_publica_y_descarta_frame_viejo(self):
        camara = self.modulo.CamaraStream(0)
        camara.frame = object()
        camara._marcar_desconectada("se perdió la señal")
        estado = camara.estado()
        self.assertEqual("se perdió la señal", estado["ultimo_error"])
        self.assertEqual(1, estado["reintentos"])
        self.assertIsNone(camara.leer()[1])


if __name__ == "__main__":
    unittest.main()
