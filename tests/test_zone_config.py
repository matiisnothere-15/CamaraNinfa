import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_modulo_sin_supervision():
    ruta = RAIZ / "modulos/vision_supervision.py"
    nombre = "vision_supervision_config_test"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    supervision_falso = types.ModuleType("supervision")
    with patch.dict(
        sys.modules,
        {"supervision": supervision_falso, nombre: modulo},
    ):
        spec.loader.exec_module(modulo)
    return modulo


class ZoneConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_modulo_sin_supervision()

    def test_zona_vacia_es_opcional(self):
        self.assertIsNone(self.modulo.parsear_poligono_normalizado(""))

    def test_parsea_poligono_normalizado(self):
        puntos = self.modulo.parsear_poligono_normalizado(
            "0.10,0.60;0.30,0.60;0.30,0.80;0.10,0.80"
        )
        self.assertEqual(4, len(puntos))
        self.assertEqual((0.1, 0.6), puntos[0])

    def test_rechaza_coordenadas_fuera_del_frame(self):
        with self.assertRaises(ValueError):
            self.modulo.parsear_poligono_normalizado("0,0;1.2,0;0,1")

    def test_rechaza_menos_de_tres_puntos(self):
        with self.assertRaises(ValueError):
            self.modulo.parsear_poligono_normalizado("0,0;1,1")


if __name__ == "__main__":
    unittest.main()
