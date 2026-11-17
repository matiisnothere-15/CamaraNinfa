import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modulos.seguridad import (
    LimitadorSolicitudes,
    es_direccion_local,
    es_solicitud_local,
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

    def test_rechaza_bypass_local_con_cabeceras_proxy_o_host_remoto(self):
        from fastapi import HTTPException
        from starlette.datastructures import Headers

        import app.servidor as servidor

        def solicitud(cabeceras, esquema="http"):
            return SimpleNamespace(
                client=SimpleNamespace(host="127.0.0.1"),
                headers=Headers(cabeceras),
                url=SimpleNamespace(scheme=esquema),
            )

        self.assertTrue(es_direccion_local("127.0.0.1:8123"))
        self.assertTrue(es_direccion_local("[::1]:8123"))
        self.assertTrue(es_direccion_local("localhost:8123"))
        self.assertFalse(
            es_solicitud_local("127.0.0.1", {"X-Forwarded-For": "203.0.113.5"})
        )
        self.assertFalse(
            es_solicitud_local("127.0.0.1", {"Host": "mi-tunel.devtunnels.ms"})
        )

        entorno_sin_clave = {
            k: v for k, v in os.environ.items() if k != "NINFAS_ADMIN_API_KEY"
        }
        with patch.dict(os.environ, entorno_sin_clave, clear=True):
            for cabeceras in (
                {"Host": "127.0.0.1:8123", "X-Forwarded-For": "203.0.113.5"},
                {"Host": "mi-tunel.devtunnels.ms"},
                {"Host": "127.0.0.1:8123", "Forwarded": "for=203.0.113.5"},
                {"Host": "127.0.0.1:8123", "X-Forwarded-Host": "mi-tunel.devtunnels.ms"},
                {"Host": "127.0.0.1:8123", "X-Original-Host": "mi-tunel.devtunnels.ms"},
            ):
                req = solicitud(cabeceras)
                with self.assertRaises(HTTPException) as ctx:
                    servidor._proteger_operacion_panel(req, None)
                self.assertEqual(403, ctx.exception.status_code)

                with self.assertRaises(HTTPException) as ctx_agente:
                    servidor._verificar_clave_agente(req, None)
                self.assertEqual(403, ctx_agente.exception.status_code)

            servidor._proteger_operacion_panel(
                solicitud({"Host": "127.0.0.1:8123"}), None
            )


if __name__ == "__main__":
    unittest.main()
