import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_modulo_sin_supervision():
    import numpy as np

    ruta = RAIZ / "modulos/vision_supervision.py"
    nombre = "vision_supervision_config_test"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    supervision_falso = types.ModuleType("supervision")

    class PositionFalsa:
        CENTER = "CENTER"

    class ColorFalso:
        def __init__(self, valor: str) -> None:
            self.valor = valor

        @classmethod
        def from_hex(cls, valor: str) -> "ColorFalso":
            return cls(valor)

    class PolygonZoneFalsa:
        def __init__(self, polygon, triggering_anchors=None) -> None:
            self.polygon = np.asarray(polygon, dtype=float)
            self.triggering_anchors = triggering_anchors
            self.current_count = 0

        def trigger(self, detections) -> np.ndarray:
            if len(detections) == 0:
                self.current_count = 0
                return np.zeros(0, dtype=bool)
            xyxy = np.asarray(detections.xyxy, dtype=float)
            cx = (xyxy[:, 0] + xyxy[:, 2]) * 0.5
            cy = (xyxy[:, 1] + xyxy[:, 3]) * 0.5
            min_x, min_y = self.polygon[:, 0].min(), self.polygon[:, 1].min()
            max_x, max_y = self.polygon[:, 0].max(), self.polygon[:, 1].max()
            mascara = (cx >= min_x) & (cx <= max_x) & (cy >= min_y) & (cy <= max_y)
            self.current_count = int(mascara.sum())
            return mascara

    class PolygonZoneAnnotatorFalso:
        def __init__(self, zone, **_kwargs) -> None:
            self.zone = zone

        def annotate(self, scene, label=""):
            return scene

    class AnnotatorFalso:
        def __init__(self, **_kwargs) -> None:
            pass

        def annotate(self, scene, detections=None, labels=None):
            return scene

    class DetectionsFalsas:
        def __init__(
            self, xyxy=None, class_id=None, confidence=None, tracker_id=None
        ) -> None:
            self.xyxy = (
                np.empty((0, 4), dtype=float)
                if xyxy is None
                else np.asarray(xyxy, dtype=float)
            )
            self.class_id = (
                None if class_id is None else np.asarray(class_id, dtype=int)
            )
            self.confidence = (
                None if confidence is None else np.asarray(confidence, dtype=float)
            )
            self.tracker_id = (
                None if tracker_id is None else np.asarray(tracker_id)
            )

        def __len__(self) -> int:
            return len(self.xyxy)

        def __getitem__(self, mascara):
            return DetectionsFalsas(
                xyxy=self.xyxy[mascara],
                class_id=None if self.class_id is None else self.class_id[mascara],
                confidence=(
                    None if self.confidence is None else self.confidence[mascara]
                ),
                tracker_id=(
                    None if self.tracker_id is None else self.tracker_id[mascara]
                ),
            )

        @classmethod
        def from_ultralytics(cls, res):
            return res

    supervision_falso.Position = PositionFalsa
    supervision_falso.Color = ColorFalso
    supervision_falso.PolygonZone = PolygonZoneFalsa
    supervision_falso.PolygonZoneAnnotator = PolygonZoneAnnotatorFalso
    supervision_falso.Detections = DetectionsFalsas
    supervision_falso.BoxAnnotator = AnnotatorFalso
    supervision_falso.LabelAnnotator = AnnotatorFalso
    supervision_falso.TraceAnnotator = AnnotatorFalso

    with patch.dict(
        sys.modules,
        {"supervision": supervision_falso, nombre: modulo},
    ):
        spec.loader.exec_module(modulo)
    return modulo


class ZoneConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_modulo_sin_supervision()

    def test_zona_vacia_es_opcional(self):
        self.assertIsNone(self.modulo.parsear_poligono_normalizado(""))

    def test_parsea_poligono_normalizado(self):
        puntos = self.modulo.parsear_poligono_normalizado(
            "0.10,0.60;0.30,0.60;0.30,0.80;0.10,0.80"
        )
        self.assertEqual(4, len(puntos))
        self.assertEqual((0.1, 0.6), puntos[0])

    def test_rechaza_coordenadas_fuera_del_frame(self):
        with self.assertRaises(ValueError):
            self.modulo.parsear_poligono_normalizado("0,0;1.2,0;0,1")

    def test_rechaza_menos_de_tres_puntos(self):
        with self.assertRaises(ValueError):
            self.modulo.parsear_poligono_normalizado("0,0;1,1")

    def test_gestor_zonas_permite_desactivar_zonas_dinamicas(self):
        with patch.dict("os.environ", {"NINFAS_ZONAS_DINAMICAS": "0"}):
            gestor = self.modulo.GestorZonas()
            self.assertFalse(gestor.permitir_dinamicas)

    def test_procesador_descarta_colision_misma_caja_ave_y_plato(self):
        import numpy as np

        procesador = self.modulo.ProcesadorDetecciones(
            nombres_clases={0: "bebedero", 1: "comedero", 2: "ninfa"},
            confianza_ninfa=0.55,
            confianza_platos=0.55,
            area_minima=800,
            area_maxima=85_000,
        )
        xyxy_ave_plato = np.array(
            [
                [100.0, 100.0, 220.0, 220.0],
                [102.0, 102.0, 218.0, 218.0],
            ]
        )
        clases_ave_plato = np.array([1, 2])  # comedero y ninfa superpuestos
        conf_ave_plato = np.array([0.60, 0.58])
        mascara_ave_plato = procesador._filtrar_colisiones_ave_plato(
            xyxy_ave_plato, clases_ave_plato, conf_ave_plato
        )
        self.assertEqual([True, True], mascara_ave_plato.tolist())

        xyxy_platos = np.array(
            [
                [100.0, 100.0, 220.0, 220.0],
                [102.0, 102.0, 218.0, 218.0],
            ]
        )
        clases_platos = np.array([0, 1])  # bebedero y comedero sobre el mismo objeto
        conf_platos = np.array([0.58, 0.72])
        mascara_platos = procesador._filtrar_colisiones_ave_plato(
            xyxy_platos, clases_platos, conf_platos
        )
        self.assertEqual([False, True], mascara_platos.tolist())

    def test_gestor_zonas_retiene_zona_dinamica_durante_oclusion(self):
        with patch.dict(
            "os.environ",
            {
                "ZONA_COMEDERO": "",
                "ZONA_BEBEDERO": "",
                "NINFAS_ZONAS_DINAMICAS": "1",
            },
        ):
            zonas = self.modulo.GestorZonas()

        Detections = self.modulo.sv.Detections
        comederos_t0 = Detections([[100.0, 100.0, 180.0, 180.0]])
        sin_detecciones = Detections()
        aves = Detections([[110.0, 110.0, 170.0, 170.0]])

        zonas.actualizar(comederos_t0, sin_detecciones, (480, 640, 3), ahora=0.0)
        en_comedero_t0, _ = zonas.evaluar(aves)
        self.assertEqual([True], en_comedero_t0.tolist())

        # Un frame posterior sin detecciones de comedero mantiene la zona activa dentro del TTL
        zonas.actualizar(sin_detecciones, sin_detecciones, (480, 640, 3), ahora=1.0)
        en_comedero_t1, _ = zonas.evaluar(aves)
        self.assertEqual([True], en_comedero_t1.tolist())

        # Tras vencer el TTL (60 s), la zona dinámica expira
        zonas.actualizar(sin_detecciones, sin_detecciones, (480, 640, 3), ahora=61.0)
        en_comedero_expirado, _ = zonas.evaluar(aves)
        self.assertEqual([False], en_comedero_expirado.tolist())

    def test_worker_async_procesa_frame_sin_bloquear(self):
        import time

        import numpy as np

        procesador = self.modulo.ProcesadorDetecciones(
            nombres_clases={0: "bebedero", 1: "comedero", 2: "ninfa"},
            confianza_ninfa=0.55,
            confianza_platos=0.55,
            area_minima=800,
            area_maxima=85_000,
        )
        try:
            frame = np.zeros((120, 160, 3), dtype=np.uint8)
            procesador.enviar_frame_async(
                frame, 7, lambda _f: (["ok"], True)
            )
            paquete = None
            for _ in range(30):
                paquete = procesador.recoger_resultado_async()
                if paquete is not None:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(paquete)
            resultados, tracking_activo, _frame_out, fid = paquete
            self.assertEqual(["ok"], resultados)
            self.assertTrue(tracking_activo)
            self.assertEqual(7, fid)
        finally:
            procesador.detener_worker_async()

    def test_suavizado_adaptativo_interpola_cajas_entre_frames(self):
        import numpy as np

        class DummyDetections:
            def __init__(self, xyxy, tracker_id, class_id):
                self.xyxy = np.array(xyxy, dtype=float)
                self.tracker_id = np.array(tracker_id)
                self.class_id = np.array(class_id)

            def __len__(self):
                return len(self.xyxy)

        vis = object.__new__(self.modulo.VisualizadorDetecciones)
        vis.alpha_suavizado = 0.38
        vis._cajas_previas = {}
        vis._edad_cajas = {}

        d1 = DummyDetections([[100.0, 100.0, 200.0, 200.0]], [1], [2])
        s1 = vis._suavizar_detecciones(d1, actualizar_estado=True)
        self.assertAlmostEqual(100.0, float(s1.xyxy[0][0]))

        # Salto grande a x1=150: debe interpolar progresivamente hacia 150
        d2 = DummyDetections([[150.0, 100.0, 250.0, 200.0]], [1], [2])
        s2 = vis._suavizar_detecciones(d2, actualizar_estado=True)
        x_f1 = float(s2.xyxy[0][0])
        self.assertGreater(x_f1, 115.0)
        self.assertLess(x_f1, 145.0)

        # Segundo frame UI antes de nueva inferencia YOLO: avanza más hacia 150
        s3 = vis._suavizar_detecciones(d2, actualizar_estado=True)
        x_f2 = float(s3.xyxy[0][0])
        self.assertGreater(x_f2, x_f1)
        self.assertLess(x_f2, 150.0)

    def test_procesador_usa_fracciones_relativas_en_1080p_y_unifica_imgsz_512(self):
        import numpy as np

        import main

        self.assertEqual(512, main.IMGSZ_INFERENCIA)

        procesador = self.modulo.ProcesadorDetecciones(
            nombres_clases={0: "bebedero", 1: "comedero", 2: "ninfa"},
            confianza_ninfa=0.55,
            confianza_platos=0.55,
        )
        frame_1080p = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # 1) Ninfa 350x300 = 105,000 px² (> 85,000, ~5.06% del frame): debe conservarse
        # 2) Ninfa enorme 800x700 = 560,000 px² (~27% > 22%): debe filtrarse
        # 3) Ninfa diminuta 20x20 = 400 px² (~0.019% < 0.05%): debe filtrarse
        detecciones = self.modulo.sv.Detections(
            xyxy=[
                [100.0, 100.0, 450.0, 400.0],
                [500.0, 100.0, 1300.0, 800.0],
                [10.0, 10.0, 30.0, 30.0],
            ],
            class_id=[2, 2, 2],
            confidence=[0.90, 0.92, 0.91],
        )

        class IdentificadorVacio:
            def resolver(self, _tracks):
                return {}

        class MovimientoVacio:
            pass

        resultado = procesador.procesar(
            [detecciones], frame_1080p, IdentificadorVacio(), MovimientoVacio()
        )
        self.assertEqual(1, len(resultado.aves))
        self.assertEqual((100, 100, 450, 400), resultado.aves_info[0].coords)

    def test_visualizador_actualiza_suavizado_solo_cuando_cambia_frame_id(self):
        import numpy as np

        vis = self.modulo.VisualizadorDetecciones(alpha_suavizado=0.5)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        det1 = self.modulo.sv.Detections(
            [[10.0, 10.0, 50.0, 50.0]], class_id=[2], tracker_id=[1]
        )
        det2 = self.modulo.sv.Detections(
            [[30.0, 10.0, 70.0, 50.0]], class_id=[2], tracker_id=[1]
        )
        res1 = self.modulo.ResultadoVision(
            detecciones=det1,
            aves=det1,
            comederos=self.modulo.sv.Detections(),
            bebederos=self.modulo.sv.Detections(),
            etiquetas=["ninfa #1"],
            aves_info=[],
        )
        res2 = self.modulo.ResultadoVision(
            detecciones=det2,
            aves=det2,
            comederos=self.modulo.sv.Detections(),
            bebederos=self.modulo.sv.Detections(),
            etiquetas=["ninfa #1"],
            aves_info=[],
        )

        vis.anotar(frame, res1, frame_id=1)
        caja_f1 = float(vis._cajas_previas[1][0])
        self.assertAlmostEqual(10.0, caja_f1)

        # Mismo frame_id: no debe mutar el estado suavizado
        vis.anotar(frame, res2, frame_id=1)
        self.assertAlmostEqual(caja_f1, float(vis._cajas_previas[1][0]))

        # Nuevo frame_id: sí debe actualizar el estado suavizado
        vis.anotar(frame, res2, frame_id=2)
        self.assertGreater(float(vis._cajas_previas[1][0]), caja_f1)

    def test_zona_detecta_pico_dentro_del_plato_aunque_la_cola_desplace_el_centro(self):
        with patch.dict(
            "os.environ",
            {
                "ZONA_COMEDERO": "0.10,0.10;0.30,0.10;0.30,0.30;0.10,0.30",
                "ZONA_BEBEDERO": "",
                "NINFAS_ZONAS_DINAMICAS": "0",
            },
        ):
            zonas = self.modulo.GestorZonas()

        Detections = self.modulo.sv.Detections
        # En frame 100x100 la zona comedero cubre [10..30, 10..30].
        # Ave 1: [20, 15, 60, 35] -> centro en (40, 25) fuera de la zona, pero
        # el tercio frontal izquierdo (x1 + 0.2*w = 28, cy = 25) sí cae dentro.
        # Ave 2: [60, 60, 90, 80] -> completamente fuera de la zona.
        aves = Detections([[20.0, 15.0, 60.0, 35.0], [60.0, 60.0, 90.0, 80.0]])
        zonas.actualizar(Detections(), Detections(), (100, 100, 3), ahora=0.0)
        en_comedero, en_bebedero = zonas.evaluar(aves)

        self.assertEqual([True, False], en_comedero.tolist())
        self.assertEqual([False, False], en_bebedero.tolist())
        self.assertEqual(1, zonas.zonas_comedero[0].zona.current_count)


if __name__ == "__main__":
    unittest.main()
