import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class SeguridadWebStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = (RAIZ / "app/servidor.py").read_text(encoding="utf-8")
        cls.http = (RAIZ / "app/seguridad_http.py").read_text(encoding="utf-8")
        cls.panel = (RAIZ / "app/static/index.html").read_text(encoding="utf-8")

    def test_api_instala_csp_hosts_y_limites(self):
        self.assertIn("Content-Security-Policy", self.http)
        self.assertIn("TrustedHostMiddleware", self.http)
        self.assertIn("LimitadorSolicitudes", self.http)
        self.assertIn("16_384", self.http)
        self.assertIn("receive_limitado", self.http)

    def test_operaciones_sensibles_exigen_dependencia(self):
        self.assertEqual(4, self.servidor.count("Depends(_proteger_operacion_panel)"))
        self.assertIn("NINFAS_ADMIN_API_KEY", self.servidor)
        self.assertIn("es_direccion_local", self.servidor)

    def test_todas_las_ventanas_horarias_tienen_limites(self):
        self.assertEqual(5, self.servidor.count("ge=1, le=168"))

    def test_panel_no_usa_eventos_inline_y_escapa_datos(self):
        self.assertNotIn("onclick=", self.panel)
        self.assertIn("function esc(valor)", self.panel)
        self.assertIn("${esc(a.nombre)}", self.panel)
        self.assertIn("${esc(r.detalle)}", self.panel)
        self.assertIn("${esc(a.notas || \"\")}", self.panel)
        self.assertNotIn("localStorage.setItem", self.panel)

    def test_panel_centraliza_respuestas_http(self):
        self.assertIn("async function api(", self.panel)
        self.assertNotIn(".then(r => r.json())", self.panel)


if __name__ == "__main__":
    unittest.main()
