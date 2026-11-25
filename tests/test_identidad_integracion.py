import unittest
from unittest.mock import patch

import numpy as np
import supervision as sv

from modulos.identificador import IdentificadorColor
from modulos.vision_supervision import ProcesadorDetecciones


class MovimientoNulo:
    def update(self, *_args):
        pass


class IdentidadIntegracionTests(unittest.TestCase):
    def test_cruce_con_ids_intercambiados_exige_identidades_nuevas(self):
        identificador = IdentificadorColor()
        identificador.configurar([
            {"id": 1, "nombre": "Mushu", "color": "gris plomo"},
            {"id": 2, "nombre": "Yukki", "color": "amarilla lutino"},
        ])
        procesador = ProcesadorDetecciones(
            {0: "ninfa", 1: "comedero", 2: "bebedero"}, 0.55, 0.55
        )
        movimiento = MovimientoNulo()
        cajas_libres = [[20, 20, 120, 120], [220, 20, 320, 120]]
        cajas_juntas = [[20, 20, 120, 120], [70, 20, 170, 120]]
        gris, amarillo = (120, 120, 120), (0, 220, 240)

        def procesar(cajas, colores):
            frame = np.full((480, 640, 3), (80, 60, 40), dtype=np.uint8)
            for (x1, y1, x2, y2), color in zip(cajas, colores, strict=True):
                frame[y1:y2, x1:x2] = color
            detecciones = sv.Detections(
                xyxy=np.array(cajas, dtype=np.float32),
                class_id=np.array([0, 0]),
                confidence=np.array([0.96, 0.95]),
                tracker_id=np.array([10, 20]),
            )
            with patch.object(sv.Detections, "from_ultralytics", return_value=detecciones):
                return procesador.procesar([object()], frame, identificador, movimiento)

        for _ in range(8):
            resultado = procesar(cajas_libres, [gris, amarillo])
        self.assertEqual(["Mushu", "Yukki"], [ave.nombre for ave in resultado.aves_info])
        resultado = procesar(cajas_juntas, [gris, amarillo])
        self.assertEqual([None, None], [ave.nombre for ave in resultado.aves_info])
        self.assertEqual({}, identificador.votos)
        for _ in range(7):
            resultado = procesar(cajas_libres, [amarillo, gris])
            self.assertEqual([None, None], [ave.nombre for ave in resultado.aves_info])
        resultado = procesar(cajas_libres, [amarillo, gris])
        self.assertEqual(["Yukki", "Mushu"], [ave.nombre for ave in resultado.aves_info])
        self.assertEqual([2, 1], [ave.ave_id for ave in resultado.aves_info])
        self.assertEqual([10, 20], [ave.track_id for ave in resultado.aves_info])
