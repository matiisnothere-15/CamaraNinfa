import unittest
from pathlib import Path

from modulos.seguridad import (
    LimitadorSolicitudes,
    es_direccion_local,
    hash_script_inline,
    limpiar_texto,
    mismo_origen,
)

RAIZ = Path(__file__).resolve().parent.parent


class SeguridadTests(unittest.TestCase):
    def test_limitador_bloquea_y_luego_libera_la_ventana(self):
        limitador = LimitadorSolicitudes()
        self.assertIsNone(limitador.registrar("ip", 2, 60, ahora=0))
        self.assertIsNone(limitador.registrar("ip", 2, 60, ahora=1))
        self.assertEqual(58, limitador.registrar("ip", 2, 60, ahora=2))
        self.assertIsNone(limitador.registrar("ip", 2, 60, ahora=61))

    def test_detecta_loopback_sin_confiar_en_nombres_arbitrarios(self):
        self.assertTrue(es_direccion_local("127.0.0.1"))
        self.assertTrue(es_direccion_local("::1"))
        self.assertFalse(es_direccion_local("192.168.1.20"))
        self.assertFalse(es_direccion_local("equipo-local"))

    def test_comparacion_de_origen_normaliza_puertos(self):
        self.assertTrue(mismo_origen("https://ninfas.example", "https", "ninfas.example:443"))
        self.assertFalse(mismo_origen("https://malicioso.example", "https", "ninfas.example"))

    def test_limpia_controles_y_normaliza_texto(self):
        self.assertEqual("Mushu", limpiar_texto("  Mu\x00shu  ", 50))
        self.assertEqual("línea 1\nlínea 2", limpiar_texto("línea 1\nlínea 2", 50, True))
        self.assertIsNone(limpiar_texto("\x00", 50))

    def test_panel_tiene_un_hash_csp_valido(self):
        resultado = hash_script_inline(RAIZ / "app/static/index.html")
        self.assertGreaterEqual(len(resultado), 40)


if __name__ == "__main__":
    unittest.main()
