import unittest

from modulos.comportamiento import (
    ConfiguracionComportamiento,
    EstadoComportamiento,
    GestorComportamiento,
    ObservacionComportamiento,
    TipoEvento,
)


def observar(track_id, estado, confianza=0.9, nombre=None):
    return ObservacionComportamiento(
        track_id=track_id,
        estado=estado,
        confianza=confianza,
        nombre_ave=nombre,
    )


class GestorComportamientoTests(unittest.TestCase):
    def setUp(self):
        self.gestor = GestorComportamiento(
            ConfiguracionComportamiento(
                confirmar_activo=1.0,
                confirmar_inactivo=10.0,
                confirmar_comiendo=2.0,
                confirmar_bebiendo=2.0,
                tolerancia_perdida=3.0,
            )
        )

    def test_comer_exige_permanencia_y_no_duplica_inicio(self):
        comida = observar(1, EstadoComportamiento.COMIENDO, nombre="Mushu")
        self.assertEqual([], self.gestor.actualizar([comida], 0.0))
        self.assertEqual([], self.gestor.actualizar([comida], 1.9))

        eventos = self.gestor.actualizar([comida], 2.0)
        self.assertEqual(1, len(eventos))
        self.assertEqual(TipoEvento.INICIO, eventos[0].tipo)
        self.assertEqual(EstadoComportamiento.COMIENDO, eventos[0].estado)
        self.assertEqual(0.0, eventos[0].timestamp)

        self.assertEqual([], self.gestor.actualizar([comida], 3.0))
        self.assertEqual([], self.gestor.actualizar([comida], 4.0))

    def test_cambio_de_comiendo_a_activo_cierra_y_abre_eventos(self):
        comida = observar(1, EstadoComportamiento.COMIENDO)
        activo = observar(1, EstadoComportamiento.ACTIVO)
        self.gestor.actualizar([comida], 0.0)
        self.gestor.actualizar([comida], 2.0)

        self.assertEqual([], self.gestor.actualizar([activo], 4.0))
        eventos = self.gestor.actualizar([activo], 5.0)

        self.assertEqual(2, len(eventos))
        self.assertEqual(
            [(TipoEvento.FIN, EstadoComportamiento.COMIENDO),
             (TipoEvento.INICIO, EstadoComportamiento.ACTIVO)],
            [(evento.tipo, evento.estado) for evento in eventos],
        )
        self.assertEqual(4.0, eventos[0].duracion)
        self.assertEqual(4.0, eventos[1].timestamp)

    def test_perdida_breve_no_cierra_el_track(self):
        activo = observar(1, EstadoComportamiento.ACTIVO)
        self.gestor.actualizar([activo], 0.0)
        self.gestor.actualizar([activo], 1.0)

        self.assertEqual([], self.gestor.actualizar([], 3.9))
        self.assertIn(1, self.gestor.tracks)

        eventos = self.gestor.actualizar([], 4.1)
        self.assertEqual(1, len(eventos))
        self.assertEqual(TipoEvento.FIN, eventos[0].tipo)
        self.assertEqual("track_perdido", eventos[0].motivo)
        self.assertNotIn(1, self.gestor.tracks)

    def test_tracks_se_actualizan_independientemente(self):
        mushu = observar(1, EstadoComportamiento.COMIENDO, nombre="Mushu")
        yukki = observar(2, EstadoComportamiento.BEBIENDO, nombre="Yukki")
        self.gestor.actualizar([mushu, yukki], 0.0)
        eventos = self.gestor.actualizar([mushu, yukki], 2.0)

        self.assertEqual(2, len(eventos))
        self.assertEqual(
            {EstadoComportamiento.COMIENDO, EstadoComportamiento.BEBIENDO},
            {evento.estado for evento in eventos},
        )
        self.assertIn("Mushu: COMIENDO", self.gestor.resumen())
        self.assertIn("Yukki: BEBIENDO", self.gestor.resumen())

    def test_inactividad_requiere_diez_segundos(self):
        inactivo = observar(3, EstadoComportamiento.INACTIVO)
        self.gestor.actualizar([inactivo], 0.0)
        self.assertEqual([], self.gestor.actualizar([inactivo], 9.9))
        eventos = self.gestor.actualizar([inactivo], 10.0)
        self.assertEqual(EstadoComportamiento.INACTIVO, eventos[0].estado)

    def test_estado_desconocido_cancela_candidato_no_confirmado(self):
        comida = observar(1, EstadoComportamiento.COMIENDO)
        desconocido = observar(1, EstadoComportamiento.DESCONOCIDO)
        self.gestor.actualizar([comida], 0.0)
        self.gestor.actualizar([desconocido], 1.0)
        self.assertEqual([], self.gestor.actualizar([comida], 2.0))
        self.assertEqual([], self.gestor.actualizar([comida], 3.9))
        eventos = self.gestor.actualizar([comida], 4.0)
        self.assertEqual(1, len(eventos))
        self.assertEqual(2.0, eventos[0].timestamp)

    def test_cierre_del_monitor_finaliza_estados_activos(self):
        activo = observar(1, EstadoComportamiento.ACTIVO)
        self.gestor.actualizar([activo], 0.0)
        self.gestor.actualizar([activo], 1.0)
        self.gestor.actualizar([activo], 5.0)

        eventos = self.gestor.cerrar_todos(6.0)
        self.assertEqual(1, len(eventos))
        self.assertEqual(TipoEvento.FIN, eventos[0].tipo)
        self.assertEqual(5.0, eventos[0].duracion)
        self.assertEqual({}, self.gestor.tracks)


if __name__ == "__main__":
    unittest.main()
