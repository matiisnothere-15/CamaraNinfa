"""La mezcla de dos ninfas no aporta votos de color ni identidades previas."""

import unittest
from unittest.mock import patch

import numpy as np
import supervision as sv

from modulos.vision_supervision import ProcesadorDetecciones


class IdentificadorRegistrado:
    def __init__(self):
        self.identidades = {10: (1, "Mushu"), 20: (2, "Yukki"), 30: (3, "Otra")}
        self.votos = []
        self.suspendidos = []
        self.tracks_resueltos = []

    def votar(self, track_id, _frame, _coords):
        self.votos.append(track_id)

    def suspender(self, track_id, ahora=None):
        self.suspendidos.append(track_id)
        self.identidades.pop(track_id, None)

    def resolver(self, tracks):
        self.tracks_resueltos.append(list(tracks))
        return {track: self.identidades[track] for track in tracks if track in self.identidades}


class MovimientoRegistrado:
    def __init__(self):
        self.tracks = []

    def update(self, track_id, *_args):
        self.tracks.append(track_id)


class OclusionesIdentidadTests(unittest.TestCase):
    def setUp(self):
        self.procesador = ProcesadorDetecciones(
            {0: "ninfa", 1: "comedero", 2: "bebedero"},
            confianza_ninfa=0.55,
            confianza_platos=0.55,
        )
        self.identificador = IdentificadorRegistrado()
        self.movimiento = MovimientoRegistrado()
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def procesar(self, cajas, clases=None, tracks=None, confianzas=None):
        cantidad = len(cajas)
        detecciones = sv.Detections(
            xyxy=np.asarray(cajas, dtype=float),
            class_id=np.asarray(clases if clases is not None else [0] * cantidad, dtype=int),
            tracker_id=np.asarray(tracks if tracks is not None else [10, 20, 30][:cantidad], dtype=int),
            confidence=np.asarray(confianzas if confianzas is not None else [0.9] * cantidad, dtype=float),
        )
        # La conversión del detector ya tiene sus propias pruebas de integración.
        with patch.object(sv.Detections, "from_ultralytics", return_value=detecciones):
            return self.procesador.procesar(
                [object()], self.frame, self.identificador, self.movimiento
            )

    def test_solapamiento_veinte_por_ciento_suspende_ambos_sin_borrar_tracks(self):
        resultado = self.procesar([[10, 10, 110, 110], [90, 10, 190, 110]])
        self.assertEqual([10, 20], self.identificador.suspendidos)
        self.assertEqual([], self.identificador.votos)
        self.assertEqual([[]], self.identificador.tracks_resueltos)
        self.assertEqual([10, 20], self.movimiento.tracks)
        self.assertEqual(2, len(resultado.detecciones))
        self.assertEqual([10, 20], [ave.track_id for ave in resultado.aves_info])
        self.assertEqual([(None, None), (None, None)], [(ave.ave_id, ave.nombre) for ave in resultado.aves_info])

    def test_ninfa_pequena_contenida_suspende_aunque_iou_sea_bajo(self):
        resultado = self.procesar([[10, 10, 110, 110], [30, 30, 50, 50]])
        self.assertEqual([10, 20], self.identificador.suspendidos)
        self.assertEqual([], self.identificador.votos)
        self.assertEqual([None, None], [ave.nombre for ave in resultado.aves_info])

    def test_ninfa_aparte_conserva_identidad_y_votos(self):
        resultado = self.procesar([
            [10, 10, 110, 110], [90, 10, 190, 110], [300, 200, 400, 300]
        ])
        self.assertEqual([10, 20], self.identificador.suspendidos)
        self.assertEqual([30], self.identificador.votos)
        self.assertEqual([[30]], self.identificador.tracks_resueltos)
        self.assertEqual([None, None, "Otra"], [ave.nombre for ave in resultado.aves_info])

    def test_separacion_reanuda_votos_sin_reasignar_identidad_suspendida(self):
        self.procesar([[10, 10, 110, 110], [90, 10, 190, 110]])
        resultado = self.procesar([[10, 10, 110, 110], [210, 10, 310, 110]])
        self.assertEqual([10, 20], self.identificador.suspendidos)
        self.assertEqual([10, 20], self.identificador.votos)
        self.assertEqual([[], [10, 20]], self.identificador.tracks_resueltos)
        self.assertEqual([None, None], [ave.nombre for ave in resultado.aves_info])

    def test_ave_sobre_plato_no_bloquea_identidad(self):
        resultado = self.procesar([[10, 10, 110, 110], [10, 10, 110, 110]], clases=[0, 1])
        self.assertEqual([], self.identificador.suspendidos)
        self.assertEqual([10], self.identificador.votos)
        self.assertEqual("Mushu", resultado.aves_info[0].nombre)
        self.assertEqual(1, len(resultado.comederos))

    def test_una_sola_caja_no_inventa_otra_ninfa(self):
        resultado = self.procesar([[10, 10, 110, 110]])
        self.assertEqual([], self.identificador.suspendidos)
        self.assertEqual([10], self.identificador.votos)
        self.assertEqual(1, len(resultado.aves_info))
        self.assertEqual("Mushu", resultado.aves_info[0].nombre)

    def test_solapamiento_menor_al_umbral_permite_votar(self):
        resultado = self.procesar([[10, 10, 110, 110], [91, 10, 191, 110]])
        self.assertEqual([], self.identificador.suspendidos)
        self.assertEqual([10, 20], self.identificador.votos)
        self.assertEqual(["Mushu", "Yukki"], [ave.nombre for ave in resultado.aves_info])

    def test_caja_descartada_por_confianza_no_bloquea_ave_valida(self):
        resultado = self.procesar(
            [[10, 10, 110, 110], [90, 10, 190, 110]], confianzas=[0.9, 0.1]
        )
        self.assertEqual([], self.identificador.suspendidos)
        self.assertEqual([10], self.identificador.votos)
        self.assertEqual(["Mushu"], [ave.nombre for ave in resultado.aves_info])


if __name__ == "__main__":
    unittest.main()
