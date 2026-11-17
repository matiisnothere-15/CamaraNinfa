import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class MainStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fuente = (RAIZ / "main.py").read_text(encoding="utf-8")
        cls.arbol = ast.parse(cls.fuente)

    def llamadas(self, nombre):
        encontradas = []
        for nodo in ast.walk(self.arbol):
            if not isinstance(nodo, ast.Call):
                continue
            funcion = nodo.func
            if isinstance(funcion, ast.Name) and funcion.id == nombre:
                encontradas.append(nodo)
            elif isinstance(funcion, ast.Attribute) and funcion.attr == nombre:
                encontradas.append(nodo)
        return encontradas

    def test_hay_un_solo_lector_de_camara(self):
        self.assertEqual(1, len(self.llamadas("CamaraStream")))
        self.assertEqual(0, len(self.llamadas("VideoCapture")))

    def test_hay_un_solo_identificador_activo(self):
        self.assertEqual(1, len(self.llamadas("IdentificadorColor")))
        self.assertNotIn("BirdIdentifier", self.fuente)

    def test_estado_global_no_esta_duplicado(self):
        self.assertEqual(1, len(self.llamadas("EstabilizadorAnimo")))
        self.assertEqual(1, len(self.llamadas("SnapshotPeriodico")))

    def test_comportamiento_es_por_track(self):
        self.assertEqual(1, len(self.llamadas("GestorComportamiento")))
        self.assertNotIn("EstadoAccion", self.fuente)

    def test_guardar_async_respeta_la_firma_de_ocho_argumentos(self):
        llamadas = self.llamadas("guardar_async")
        self.assertTrue(llamadas)
        self.assertTrue(all(len(llamada.args) <= 8 for llamada in llamadas))

    def test_persistencia_usa_una_cola_y_no_un_hilo_por_evento(self):
        self.assertIn("obtener_cola_escritura", self.fuente)
        self.assertIn("COLA_BD.encolar", self.fuente)
        self.assertNotIn("threading.Thread", self.fuente)

    def test_soporta_modo_headless_para_servidor_dedicado(self):
        self.assertIn("es_modo_headless", self.fuente)
        self.assertIn("NINFAS_HEADLESS", self.fuente)
        self.assertEqual(1, len(self.llamadas("es_modo_headless")))


if __name__ == "__main__":
    unittest.main()
