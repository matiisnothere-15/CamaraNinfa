import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_identificador_sin_opencv():
    ruta = RAIZ / "modulos/identificador.py"
    nombre = "identificador_test_module"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    cv2_falso = types.ModuleType("cv2")
    with patch.dict(sys.modules, {"cv2": cv2_falso, nombre: modulo}):
        spec.loader.exec_module(modulo)
    return modulo


class IdentificadorColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_identificador_sin_opencv()

    def crear(self):
        identificador = self.modulo.IdentificadorColor()
        activo = identificador.configurar(
            [
                {"id": 1, "nombre": "Mushu", "color": "gris plomo"},
                {"id": 2, "nombre": "Yukki", "color": "amarilla lutino"},
            ]
        )
        self.assertTrue(activo)
        return identificador

    def votar(self, identificador, track_id, tipo, cantidad):
        for indice in range(cantidad):
            identificador.registrar_voto(track_id, tipo, ahora=float(indice))

    def test_tipos_distintos_reciben_identidades_distintas(self):
        identificador = self.crear()
        self.votar(identificador, 10, "gris", 8)
        self.votar(identificador, 20, "amarilla", 8)

        asignaciones = identificador.resolver([10, 20], ahora=7.0)
        self.assertEqual((1, "Mushu"), asignaciones[10])
        self.assertEqual((2, "Yukki"), asignaciones[20])

    def test_un_nombre_no_se_asigna_a_dos_tracks(self):
        identificador = self.crear()
        self.votar(identificador, 10, "gris", 8)
        self.votar(identificador, 20, "gris", 10)

        asignaciones = identificador.resolver([10, 20], ahora=9.0)
        self.assertNotIn(10, asignaciones)
        self.assertEqual((1, "Mushu"), asignaciones[20])

    def test_sin_color_infrarrojo_no_conserva_nombre(self):
        identificador = self.crear()
        self.votar(identificador, 10, "gris", 8)
        identificador.color_disponible[10] = False

        self.assertEqual({}, identificador.resolver([10], ahora=7.0))
        self.assertEqual((None, None), identificador.identificar(10))

    def test_tracks_antiguos_se_eliminan(self):
        identificador = self.crear()
        self.votar(identificador, 10, "gris", 8)
        identificador.limpiar(ahora=200.0)
        self.assertNotIn(10, identificador.votos)

    def test_sincronizar_aves_en_caliente_actualiza_ids_sin_perder_votos(self):
        identificador = self.modulo.IdentificadorColor()
        identificador.configurar(
            [
                {"id": None, "nombre": "Mushu", "color": "gris plomo"},
                {"id": None, "nombre": "Yukki", "color": "amarilla lutino"},
            ]
        )
        self.votar(identificador, 10, "gris", 8)
        self.assertEqual((None, "Mushu"), identificador.resolver([10], ahora=7.0)[10])

        cambio = identificador.sincronizar_aves(
            [
                {"id": 15, "nombre": "Mushu", "color": "gris plomo"},
                {"id": 16, "nombre": "Yukki", "color": "amarilla lutino"},
            ]
        )
        self.assertTrue(cambio)
        self.assertEqual((15, "Mushu"), identificador.resolver([10], ahora=8.0)[10])
        self.assertFalse(
            identificador.sincronizar_aves(
                [
                    {"id": 15, "nombre": "Mushu", "color": "gris plomo"},
                    {"id": 16, "nombre": "Yukki", "color": "amarilla lutino"},
                ]
            )
        )

    def test_ave_blanca_albina_se_separa_de_amarilla_y_gris(self):
        import numpy as np

        from modulos.identificador import IdentificadorColor

        mapa = self.modulo.IdentificadorColor._construir_mapa_aves(
            [
                {"id": 1, "nombre": "Mushu", "color": "gris plomo"},
                {"id": 2, "nombre": "Yukki", "color": "amarilla lutino"},
                {"id": 3, "nombre": "Copito", "color": "blanca albina"},
            ]
        )
        self.assertEqual("Mushu", mapa["gris"]["nombre"])
        self.assertEqual("Yukki", mapa["amarilla"]["nombre"])
        self.assertEqual("Copito", mapa["blanca"]["nombre"])

        frame_amarillo = np.full((80, 80, 3), (0, 220, 240), dtype=np.uint8)
        frame_blanco = np.full((80, 80, 3), (235, 235, 235), dtype=np.uint8)
        frame_gris = np.full((80, 80, 3), (120, 120, 120), dtype=np.uint8)

        self.assertEqual(
            "amarilla", IdentificadorColor.clasificar_color(frame_amarillo, (0, 0, 80, 80))
        )
        self.assertEqual(
            "blanca", IdentificadorColor.clasificar_color(frame_blanco, (0, 0, 80, 80))
        )
        self.assertEqual(
            "gris", IdentificadorColor.clasificar_color(frame_gris, (0, 0, 80, 80))
        )


if __name__ == "__main__":
    unittest.main()
