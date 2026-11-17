import unittest

from modulos.notificaciones import NotificadorAlertas


class NotificacionesTests(unittest.TestCase):
    def test_inactivo_por_defecto_sin_credenciales(self):
        notificador = NotificadorAlertas(
            webhook_url="", telegram_token="", telegram_chat_id=""
        )
        self.assertFalse(notificador.activo)
        self.assertFalse(
            notificador.enviar_sincrono("sin_comer:Yukki", "! YUKKI SIN COMER: 4.1h")
        )

    def test_rechaza_webhook_remoto_sin_https(self):
        notificador = NotificadorAlertas(
            webhook_url="http://ejemplo.com/webhook",
            telegram_token="",
            telegram_chat_id="",
        )
        self.assertIsNone(notificador.webhook_url)
        self.assertFalse(notificador.activo)

    def test_envia_webhook_y_telegram_con_prefijo_de_nivel(self):
        llamadas = []

        def enviador_falso(url, payload):
            llamadas.append((url, payload))
            return True

        notificador = NotificadorAlertas(
            webhook_url="https://hooks.example.com/alerta",
            telegram_token="123456:TOKEN",
            telegram_chat_id="987654",
            cooldown_segundos=1800,
            enviador_http=enviador_falso,
        )
        self.assertTrue(notificador.activo)

        exito = notificador.enviar_sincrono(
            "sin_comer:Yukki",
            "! YUKKI SIN COMER: 4.2h (ingesta sin ID reciente)",
            nivel="vigilancia",
            ahora=100.0,
        )
        self.assertTrue(exito)
        self.assertEqual(2, len(llamadas))
        self.assertIn("[VIGILANCIA CLINICA]", llamadas[0][1]["content"])
        self.assertEqual("987654", llamadas[1][1]["chat_id"])

    def test_respeta_cooldown_por_clave_y_permite_claves_distintas(self):
        llamadas = []
        notificador = NotificadorAlertas(
            webhook_url="https://hooks.example.com/alerta",
            telegram_token="",
            telegram_chat_id="",
            cooldown_segundos=600,
            enviador_http=lambda url, payload: llamadas.append((url, payload)) or True,
        )

        self.assertTrue(
            notificador.enviar_sincrono("sin_comer:Yukki", "Alerta 1", ahora=100.0)
        )
        # Misma clave dentro de la ventana de 600s -> no reenvía
        self.assertFalse(
            notificador.enviar_sincrono("sin_comer:Yukki", "Alerta 1 dup", ahora=400.0)
        )
        # Otra ave o clave distinta -> sí envía
        self.assertTrue(
            notificador.enviar_sincrono("sin_beber:Mushu", "Alerta 2", ahora=400.0)
        )
        # Pasado el cooldown de 600s -> vuelve a enviar
        self.assertTrue(
            notificador.enviar_sincrono("sin_comer:Yukki", "Alerta 1 reenvio", ahora=800.0)
        )
        self.assertEqual(3, len(llamadas))

    def test_cola_asincrona_despacha_y_cierra_limpiamente(self):
        recibidos = []
        notificador = NotificadorAlertas(
            webhook_url="https://hooks.example.com/alerta",
            telegram_token="",
            telegram_chat_id="",
            cooldown_segundos=0,
            enviador_http=lambda url, payload: recibidos.append(payload["clave"]) or True,
        )
        self.assertTrue(
            notificador.notificar_async("animo:Desesperado", "Ave desesperada")
        )
        notificador.stop()
        self.assertEqual(["animo:Desesperado"], recibidos)


if __name__ == "__main__":
    unittest.main()
