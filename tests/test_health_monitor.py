import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from modulos.comportamiento import (
    EstadoComportamiento,
    EventoComportamiento,
    TipoEvento,
)
from modulos.health_monitor import HealthMonitor


def _cargar_procesar_eventos_comportamiento():
    ruta_main = Path(__file__).resolve().parent.parent / "main.py"
    arbol = ast.parse(ruta_main.read_text(encoding="utf-8"), filename=str(ruta_main))
    nodo_fn = next(
        nodo
        for nodo in arbol.body
        if isinstance(nodo, ast.FunctionDef)
        and nodo.name == "procesar_eventos_comportamiento"
    )
    modulo_ast = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations", asname=None)],
                level=0,
            ),
            nodo_fn,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(modulo_ast)
    espacio = {
        "EstadoComportamiento": EstadoComportamiento,
        "EventoComportamiento": EventoComportamiento,
        "TipoEvento": TipoEvento,
        "HealthMonitor": HealthMonitor,
        "guardar_async": lambda *_args, **_kwargs: None,
    }
    exec(compile(modulo_ast, filename=str(ruta_main), mode="exec"), espacio)
    return espacio["procesar_eventos_comportamiento"]


class HealthMonitorTests(unittest.TestCase):
    def crear_monitor(self, sensibilidad_clinica: bool = True) -> HealthMonitor:
        with patch("modulos.health_monitor.time.time", return_value=0.0):
            return HealthMonitor(
                ["Mushu", "Yukki"], sensibilidad_clinica=sensibilidad_clinica
            )

    def test_alerta_despues_de_cuatro_horas(self):
        monitor = self.crear_monitor()

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            alertas = monitor.check_health()
            tipos = {alerta["tipo"] for alerta in alertas}
            niveles = {alerta["nivel"] for alerta in alertas}

        self.assertIn("sin_comer:Mushu", tipos)
        self.assertIn("sin_beber:Yukki", tipos)
        self.assertEqual({"critica"}, niveles)

    def test_accion_identificada_actualiza_solo_un_ave(self):
        monitor = self.crear_monitor()
        with patch("modulos.health_monitor.time.time", return_value=1_000.0):
            monitor.register_action("Alimentacion", "Mushu")

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}

        self.assertNotIn("sin_comer:Mushu", tipos)
        self.assertIn("sin_comer:Yukki", tipos)

    def test_sensibilidad_clinica_mantiene_alerta_en_vigilancia_ante_accion_sin_id(self):
        monitor = self.crear_monitor(sensibilidad_clinica=True)
        with patch("modulos.health_monitor.time.time", return_value=1_000.0):
            monitor.register_action("Alimentacion", "?")

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            alertas_comida = [
                a for a in monitor.check_health() if a["tipo"].startswith("sin_comer:")
            ]

        self.assertEqual(2, len(alertas_comida))
        self.assertTrue(all(a["nivel"] == "vigilancia" for a in alertas_comida))
        self.assertTrue(
            all("sin ID reciente" in a["texto"] for a in alertas_comida)
        )

    def test_modo_conservador_opcional_actualiza_todas_las_aves_sin_id(self):
        monitor = self.crear_monitor(sensibilidad_clinica=False)
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

    def test_sincronizar_aves_conserva_contadores_existentes(self):
        monitor = self.crear_monitor()
        with patch("modulos.health_monitor.time.time", return_value=500.0):
            monitor.register_action("Alimentacion", "Mushu")
            cambio = monitor.sincronizar_aves(["Mushu", "Yukki", "Koko"])

        self.assertTrue(cambio)
        self.assertEqual(500.0, monitor.registro["Mushu"]["comer"])
        self.assertEqual(500.0, monitor.registro["Koko"]["comer"])

    def test_evento_fin_con_identidad_tardia_actualiza_registro_individual(self):
        procesar_eventos_comportamiento = _cargar_procesar_eventos_comportamiento()
        salud = self.crear_monitor()
        evento_inicio = EventoComportamiento(
            track_id=1,
            estado=EstadoComportamiento.COMIENDO,
            tipo=TipoEvento.INICIO,
            timestamp=2.0,
            duracion=0.0,
            confianza=0.9,
            ave_id=None,
            nombre_ave=None,
            motivo="confirmado",
        )
        evento_fin = EventoComportamiento(
            track_id=1,
            estado=EstadoComportamiento.COMIENDO,
            tipo=TipoEvento.FIN,
            timestamp=10.0,
            duracion=8.0,
            confianza=0.9,
            ave_id=1,
            nombre_ave="Yukki",
            motivo="cambio_estado",
        )

        with patch("modulos.health_monitor.time.time", return_value=2.0):
            procesar_eventos_comportamiento([evento_inicio], salud)
        self.assertEqual(0.0, salud.registro["Yukki"]["comer"])

        with patch("modulos.health_monitor.time.time", return_value=10.0):
            procesar_eventos_comportamiento([evento_fin], salud)
        self.assertEqual(10.0, salud.registro["Yukki"]["comer"])

    def test_ocho_horas_en_modo_nocturno_no_disparan_alertas_criticas(self):
        monitor = self.crear_monitor()
        with patch("modulos.health_monitor.time.time", return_value=0.0):
            self.assertFalse(
                monitor.actualizar_condiciones(camara_conectada=True, luz_diurna=False)
            )

        with patch("modulos.health_monitor.time.time", return_value=14_401.0):
            self.assertEqual([], monitor.check_health())

        with patch("modulos.health_monitor.time.time", return_value=28_800.0):
            self.assertEqual([], monitor.check_health())
            stats = monitor.get_stats()
            self.assertEqual(0.0, stats["eating_sec"])
            self.assertEqual(0.0, stats["drinking_sec"])
            self.assertTrue(
                monitor.actualizar_condiciones(camara_conectada=True, luz_diurna=True)
            )
            self.assertEqual([], monitor.check_health())

        with patch("modulos.health_monitor.time.time", return_value=43_201.0):
            tipos = {alerta["tipo"] for alerta in monitor.check_health()}
            self.assertIn("sin_comer:Mushu", tipos)
            self.assertIn("sin_beber:Yukki", tipos)

    def test_brecha_sin_monitoreo_al_arrancar_no_dispara_alerta_en_segundo_cero(self):
        with patch("modulos.health_monitor.time.time", return_value=50_000.0):
            monitor = HealthMonitor(
                ["Mushu", "Yukki"],
                estado_inicial={
                    "Mushu": {"comer": 10_000.0, "beber": 10_000.0},
                    "__ultimo_snapshot__": 48_000.0,
                },
            )
            self.assertTrue(monitor.observacion_tras_apagado)
            self.assertEqual(50_000.0, monitor.registro["Mushu"]["comer"])
            self.assertEqual([], monitor.check_health())


if __name__ == "__main__":
    unittest.main()
