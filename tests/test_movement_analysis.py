import unittest

from modulos.movement_analysis import MovementMonitor


class MovementMonitorTests(unittest.TestCase):
    def trayectoria(self, ancho, alto):
        monitor = MovementMonitor(smoothing_alpha=1.0)
        monitor.update(1, ancho * 0.1, alto * 0.5, ancho, alto, now=0.0)
        monitor.update(1, ancho * 0.2, alto * 0.5, ancho, alto, now=5.0)
        monitor.update(1, ancho * 0.3, alto * 0.5, ancho, alto, now=10.0)
        return monitor.get_activity_level(1, now=10.0)

    def test_valor_es_independiente_de_la_resolucion(self):
        nivel_720, valor_720 = self.trayectoria(1280, 720)
        nivel_1080, valor_1080 = self.trayectoria(1920, 1080)
        self.assertEqual(nivel_720, nivel_1080)
        self.assertAlmostEqual(valor_720, valor_1080, places=6)

    def test_requiere_ventana_minima(self):
        monitor = MovementMonitor(smoothing_alpha=1.0)
        monitor.update(1, 100, 100, 1000, 1000, now=0.0)
        monitor.update(1, 200, 100, 1000, 1000, now=1.0)
        self.assertEqual(("Desconocido", 0.0), monitor.get_activity_level(1, now=1.0))

    def test_posicion_estable_es_sedentaria(self):
        monitor = MovementMonitor(smoothing_alpha=1.0)
        monitor.update(1, 100, 100, 1000, 1000, now=0.0)
        monitor.update(1, 100, 100, 1000, 1000, now=5.0)
        self.assertEqual("Sedentario", monitor.get_activity_level(1, now=5.0)[0])

    def test_track_viejo_no_contamina_actividad_global(self):
        monitor = MovementMonitor(stale_track_seconds=5.0, smoothing_alpha=1.0)
        monitor.update(1, 100, 100, 1000, 1000, now=0.0)
        self.assertEqual(("Sin datos", 0.0), monitor.get_global_activity(now=6.0))
        self.assertNotIn(1, monitor.tracks)


if __name__ == "__main__":
    unittest.main()
