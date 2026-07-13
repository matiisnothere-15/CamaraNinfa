import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def llamadas(arbol, nombre):
    encontradas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        if isinstance(funcion, ast.Name) and funcion.id == nombre:
            encontradas.append(nodo)
        elif isinstance(funcion, ast.Attribute) and funcion.attr == nombre:
            encontradas.append(nodo)
    return encontradas


class SupervisionStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_fuente = (RAIZ / "main.py").read_text(encoding="utf-8")
        cls.vision_fuente = (RAIZ / "modulos/vision_supervision.py").read_text(
            encoding="utf-8"
        )
        cls.main = ast.parse(cls.main_fuente)
        cls.vision = ast.parse(cls.vision_fuente)

    def test_main_crea_una_sola_capa_supervision(self):
        self.assertEqual(1, len(llamadas(self.main, "ProcesadorDetecciones")))
        self.assertEqual(1, len(llamadas(self.main, "VisualizadorDetecciones")))
        self.assertEqual(1, len(llamadas(self.main, "GestorZonas")))

    def test_conversion_desde_ultralytics_esta_centralizada(self):
        self.assertEqual(1, len(llamadas(self.vision, "from_ultralytics")))
        self.assertNotIn("from_ultralytics", self.main_fuente)

    def test_identidades_se_resuelven_en_conjunto(self):
        self.assertEqual(1, len(llamadas(self.vision, "resolver")))
        self.assertEqual(0, len(llamadas(self.vision, "identificar")))

    def test_usa_anotadores_y_polygon_zone(self):
        for nombre in ("BoxAnnotator", "LabelAnnotator", "TraceAnnotator", "PolygonZone"):
            self.assertTrue(llamadas(self.vision, nombre), nombre)

    def test_main_ya_no_dibuja_cajas_manualmente(self):
        self.assertEqual(0, len(llamadas(self.main, "rectangle")))

    def test_zonas_estan_documentadas_en_env(self):
        ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ZONA_COMEDERO=", ejemplo)
        self.assertIn("ZONA_BEBEDERO=", ejemplo)


if __name__ == "__main__":
    unittest.main()
