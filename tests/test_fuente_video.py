import os
import unittest
from unittest.mock import patch

from modulos.fuente_video import (
    construir_url_tapo,
    describir_fuente,
    es_rtsp,
    parsear_fuente,
    resolver_fuente,
)


class FuenteVideoTests(unittest.TestCase):
    def test_parsea_indice_y_url(self):
        self.assertEqual(2, parsear_fuente("2"))
        self.assertEqual("http://camara/video", parsear_fuente("http://camara/video"))

    def test_rechaza_fuente_invalida(self):
        with self.assertRaises(ValueError):
            parsear_fuente("camara-sin-esquema")

    def test_url_tapo_escapa_credenciales(self):
        url = construir_url_tapo("ave@casa", "clave:/?", "192.168.1.20")
        self.assertEqual(
            "rtsp://ave%40casa:clave%3A%2F%3F@192.168.1.20:554/stream2",
            url,
        )

    def test_tapo_parcial_es_error(self):
        with patch.dict(os.environ, {"TAPO_USER": "usuario"}, clear=True):
            with self.assertRaises(ValueError):
                construir_url_tapo()

    def test_prioriza_url_generica_y_oculta_credenciales(self):
        entorno = {"CAMARA_RTSP_URL": "rtsp://usuario:secreto@camara:8554/video"}
        with patch.dict(os.environ, entorno, clear=True):
            fuente = resolver_fuente()
        self.assertTrue(es_rtsp(fuente))
        descripcion = describir_fuente(fuente)
        self.assertEqual("rtsp://camara:8554/video", descripcion)
        self.assertNotIn("secreto", descripcion)

    def test_recurre_a_webcam(self):
        with patch.dict(os.environ, {"CAMARA_PC_INDICE": "3"}, clear=True):
            self.assertEqual(3, resolver_fuente())


if __name__ == "__main__":
    unittest.main()
