import unittest
from unittest.mock import patch

from modulos.estado_monitor import EstabilizadorAnimo, SnapshotPeriodico


class EstabilizadorAnimoTests(unittest.TestCase):
    def test_exige_tiempo_de_confirmacion(self):
        with patch("modulos.estado_monitor.time.monotonic", return_value=0.0):
            estabilizador = EstabilizadorAnimo(segundos_confirmacion=10.0)

        with patch("modulos.estado_monitor.time.monotonic", return_value=5.0):
            estado, cambio = estabilizador.actualizar("Estresado")
        self.assertEqual("Normal", estado)
        self.assertFalse(cambio)

        with patch("modulos.estado_monitor.time.monotonic", return_value=16.0):
            estado, cambio = estabilizador.actualizar("Estresado")
        self.assertEqual("Estresado", estado)
        self.assertTrue(cambio)


class SnapshotPeriodicoTests(unittest.TestCase):
    def test_arma_las_cinco_metricas_base(self):
        with patch("modulos.estado_monitor.time.monotonic", return_value=0.0):
            snapshot = SnapshotPeriodico(intervalo_segundos=300)
            filas = snapshot.armar_filas(
                "Normal",
                "Actividad Normal",
                120.0,
                {"status": "Sonidos", "rms": 0.03, "freq": 900.0},
                {"eating_sec": 3_600.0, "drinking_sec": 7_200.0},
            )

        self.assertEqual(
            {"EstadoAnimo", "Actividad", "Audio", "SinComer", "SinBeber"},
            {fila[1] for fila in filas},
        )
        actividad = next(fila for fila in filas if fila[1] == "Actividad")
        self.assertEqual("%diagonal/min", actividad[5])

    def test_intervalo_snapshot_se_lee_desde_entorno_con_minimo_seguro(self):
        with patch.dict("os.environ", {"NINFAS_SNAPSHOT_INTERVALO": "900"}):
            self.assertEqual(900, SnapshotPeriodico().intervalo)
        with patch.dict("os.environ", {"NINFAS_SNAPSHOT_INTERVALO": "10"}):
            self.assertEqual(60, SnapshotPeriodico().intervalo)

    def test_reloj_monotonico_es_inmune_a_saltos_ntp_de_time(self):
        with (
            patch("modulos.estado_monitor.time.monotonic", return_value=100.0),
            patch("modulos.estado_monitor.time.time", return_value=1_000.0),
        ):
            estabilizador = EstabilizadorAnimo(segundos_confirmacion=10.0)
            snapshot = SnapshotPeriodico(intervalo_segundos=300)

        with (
            patch("modulos.estado_monitor.time.monotonic", return_value=101.0),
            patch("modulos.estado_monitor.time.time", return_value=4_600.0),
        ):
            estado, cambio = estabilizador.actualizar("Estresado")
            self.assertEqual("Normal", estado)
            self.assertFalse(cambio)
            self.assertFalse(snapshot.toca_guardar())


if __name__ == "__main__":
    unittest.main()
