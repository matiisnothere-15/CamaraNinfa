import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_herramienta():
    ruta = RAIZ / "tools" / "configurar_zonas.py"
    nombre = "configurar_zonas_tool_test"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"cv2": types.ModuleType("cv2"), nombre: modulo}):
        spec.loader.exec_module(modulo)
    return modulo


class ConfigurarZonasToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_herramienta()

    def test_normaliza_puntos(self):
        resultado = self.modulo.normalizar([(0, 0), (320, 240), (640, 480)], 640, 480)
        self.assertEqual("0.000000,0.000000;0.500000,0.500000;1.000000,1.000000", resultado)

    def test_rechaza_menos_de_tres_puntos(self):
        with self.assertRaises(ValueError):
            self.modulo.normalizar([(0, 0), (10, 10)], 640, 480)


if __name__ == "__main__":
    unittest.main()
