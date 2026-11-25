import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from modulos.identificador import IdentificadorColor


class IdentidadContraluzTests(unittest.TestCase):
    def crear(self):
        identificador = IdentificadorColor()
        identificador.configurar([
            {"id": 1, "nombre": "Mushu", "color": "gris plomo"},
            {"id": 2, "nombre": "Yukki", "color": "amarilla lutino"},
        ])
        return identificador

    def cargar_yukki(self):
        ruta = Path(__file__).parent / "fixtures/yukki_contraluz.png"
        imagen = cv2.imread(str(ruta))
        self.assertIsNotNone(imagen)
        return imagen

    def test_captura_real_de_yukki_no_se_clasifica_como_mushu(self):
        imagen = self.cargar_yukki()
        self.assertEqual(
            "amarilla", IdentificadorColor.clasificar_color(imagen, (180, 140, 581, 540))
        )
        identificador = self.crear()
        for i in range(8):
            identificador.votar(18, imagen, (180, 140, 581, 540), ahora=float(i))
        self.assertEqual((2, "Yukki"), identificador.resolver([18], ahora=7)[18])

    def test_yukki_con_menos_luz_no_se_convierte_en_gris(self):
        imagen = (self.cargar_yukki().astype(float) * 0.8).astype(np.uint8)
        self.assertNotEqual(
            "gris", IdentificadorColor.clasificar_color(imagen, (180, 140, 581, 540))
        )

    def test_captura_real_tol_reencuadre_y_exposicion_sin_inventar_gris(self):
        imagen = self.cargar_yukki()
        for factor in (0.8, 1.0, 1.15):
            variante = np.clip(imagen.astype(float) * factor, 0, 255).astype(np.uint8)
            for dx, dy in ((-10, 0), (10, 0), (0, -10), (0, 10)):
                with self.subTest(exposicion=factor, desplazamiento=(dx, dy)):
                    self.assertNotEqual(
                        "gris", IdentificadorColor.clasificar_color(
                            variante, (180 + dx, 140 + dy, 581 + dx, 540 + dy)
                        )
                    )

    def test_caja_fusionada_con_dos_plumajes_no_impone_identidad(self):
        imagen = np.full((120, 120, 3), (0, 220, 240), dtype=np.uint8)
        imagen[:, 60:] = 120
        self.assertIsNone(IdentificadorColor.clasificar_color(imagen, (0, 0, 120, 120)))

    def test_gris_claro_sin_evidencia_suficiente_queda_indeterminado(self):
        imagen = np.full((120, 120, 3), 165, dtype=np.uint8)
        self.assertIsNone(IdentificadorColor.clasificar_color(imagen, (0, 0, 120, 120)))

    def test_muestra_historica_gris_y_lutino_siguen_distinguiendose(self):
        ruta = (Path(__file__).parent.parent / "entrenamiento/test/images"
                / "ninfa_ef589a73_jpg.rf.ef103c1ca396dc3d1bb7b59ef22e6801.jpg")
        imagen = cv2.imread(str(ruta))
        self.assertIsNotNone(imagen)
        self.assertEqual("gris", IdentificadorColor.clasificar_color(imagen, (129, 325, 254, 437)))
        self.assertEqual("amarilla", IdentificadorColor.clasificar_color(imagen, (236, 380, 356, 452)))

    def test_suspender_exige_ocho_votos_nuevos_al_separarse(self):
        identificador = self.crear()
        for i in range(8):
            identificador.registrar_voto(18, "gris", ahora=float(i))
        self.assertEqual((1, "Mushu"), identificador.resolver([18], ahora=7)[18])
        identificador.suspender(18, ahora=8)
        self.assertEqual({}, identificador.resolver([18], ahora=8))
        for i in range(7):
            identificador.registrar_voto(18, "amarilla", ahora=9.0 + i)
        self.assertEqual({}, identificador.resolver([18], ahora=15))
        identificador.registrar_voto(18, "amarilla", ahora=16)
        self.assertEqual((2, "Yukki"), identificador.resolver([18], ahora=16)[18])

    def test_color_ambiguo_no_conserva_identidad_vieja(self):
        identificador = self.crear()
        for i in range(8):
            identificador.registrar_voto(18, "gris", ahora=float(i))
        identificador.resolver([18], ahora=7)
        with (
            patch.object(identificador, "frame_tiene_color", return_value=True),
            patch.object(identificador, "clasificar_color", return_value=None),
        ):
            identificador.votar(18, np.zeros((10, 10, 3), dtype=np.uint8), (0, 0, 10, 10), ahora=8)
        self.assertEqual({}, identificador.resolver([18], ahora=8))

    def test_color_contradictorio_retira_nombre_y_requiere_confirmacion(self):
        identificador = self.crear()
        for i in range(8):
            identificador.registrar_voto(18, "gris", ahora=float(i))
        identificador.resolver([18], ahora=7)
        imagen = np.zeros((10, 10, 3), dtype=np.uint8)
        with (
            patch.object(identificador, "frame_tiene_color", return_value=True),
            patch.object(identificador, "clasificar_color", return_value="amarilla"),
        ):
            identificador.votar(18, imagen, (0, 0, 10, 10), ahora=8)
            self.assertEqual({}, identificador.resolver([18], ahora=8))
            for i in range(7):
                identificador.votar(18, imagen, (0, 0, 10, 10), ahora=9.0 + i)
        self.assertEqual((2, "Yukki"), identificador.resolver([18], ahora=15)[18])

    def test_cambio_de_color_antes_de_confirmar_no_aprovecha_votos_del_otro(self):
        identificador = self.crear()
        for i in range(7):
            identificador.registrar_voto(18, "gris", ahora=float(i))
        with (
            patch.object(identificador, "frame_tiene_color", return_value=True),
            patch.object(identificador, "clasificar_color", return_value="amarilla"),
        ):
            identificador.votar(18, np.zeros((10, 10, 3), dtype=np.uint8), (0, 0, 10, 10), ahora=8)
        self.assertEqual({}, identificador.resolver([18], ahora=8))

    def test_reaparicion_tras_expirar_track_no_recupera_votos_antiguos(self):
        identificador = self.crear()
        for i in range(8):
            identificador.registrar_voto(18, "gris", ahora=float(i))
        identificador.resolver([18], ahora=7)
        with (
            patch.object(identificador, "frame_tiene_color", return_value=True),
            patch.object(identificador, "clasificar_color", return_value="gris"),
        ):
            identificador.votar(18, np.zeros((10, 10, 3), dtype=np.uint8), (0, 0, 10, 10), ahora=200)
        self.assertEqual({}, identificador.resolver([18], ahora=200))
