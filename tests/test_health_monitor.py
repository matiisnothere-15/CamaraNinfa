import unittest
from unittest.mock import patch

from modulos.health_monitor import HealthMonitor


class HealthMonitorTests(unittest.TestCase):
    def crear_monitor(self) -> HealthMonitor:
        with patch("modulos.health_monitor.time.time", return_value=0.0):
            return HealthMonitor(["Mushu", "Yukki"])

    def test_alerta_despues_de_cuatro_horas(self):
        monitor = self.crear_monitor()

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}

        self.assertIn("sin_comer:Mushu", tipos)
        self.assertIn("sin_beber:Yukki", tipos)

    def test_accion_identificada_actualiza_solo_un_ave(self):
        monitor = self.crear_monitor()
        with patch("modulos.health_monitor.time.time", return_value=1_000.0):
            monitor.register_action("Alimentacion", "Mushu")

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}

        self.assertNotIn("sin_comer:Mushu", tipos)
        self.assertIn("sin_comer:Yukki", tipos)

    def test_accion_sin_identidad_actualiza_todas_las_aves(self):
        monitor = self.crear_monitor()
        with patch("modulos.health_monitor.time.time", return_value=1_000.0):
            monitor.register_action("Alimentacion", "?")

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}

        self.assertNotIn("sin_comer:Mushu", tipos)
        self.assertNotIn("sin_comer:Yukki", tipos)

    def test_restaura_el_ultimo_consumo_sin_reiniciar_contadores(self):
        with patch("modulos.health_monitor.time.time", return_value=20_000.0):
            monitor = HealthMonitor(
                ["Mushu"],
                estado_inicial={"Mushu": {"comer": 1_000.0, "beber": 19_000.0}},
            )

        with patch("modulos.health_monitor.time.time", return_value=20_000.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}

        self.assertIn("sin_comer:Mushu", tipos)
        self.assertNotIn("sin_beber:Mushu", tipos)

    def test_descarta_timestamp_futuro(self):
        with patch("modulos.health_monitor.time.time", return_value=100.0):
            monitor = HealthMonitor(
                ["Mushu"], estado_inicial={"Mushu": {"comer": 999.0}}
            )
        self.assertEqual(100.0, monitor.registro["Mushu"]["comer"])


if __name__ == "__main__":
    unittest.main()
