import importlib.util
import sys
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


def cargar_camara_sin_opencv():
    try:
        import numpy  # noqa: F401
    except ImportError:
        pass
    ruta = RAIZ / "modulos/camara.py"
    nombre = "camara_test_module"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    cv2_falso = types.ModuleType("cv2")
    with patch.dict(sys.modules, {"cv2": cv2_falso, nombre: modulo}):
        spec.loader.exec_module(modulo)
    return modulo


class CamaraEstadoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modulo = cargar_camara_sin_opencv()

    def test_estado_inicial_es_desconectado(self):
        camara = self.modulo.CamaraStream(0)
        estado = camara.estado()
        self.assertFalse(estado["conectada"])
        self.assertEqual(0, estado["reintentos"])
        self.assertEqual((0, None), camara.leer())

    def test_error_se_publica_y_descarta_frame_viejo(self):
        camara = self.modulo.CamaraStream(0)
        camara.frame = object()
        camara._marcar_desconectada("se perdió la señal")
        estado = camara.estado()
        self.assertEqual("se perdió la señal", estado["ultimo_error"])
        self.assertEqual(1, estado["reintentos"])
        self.assertIsNone(camara.leer()[1])

    def test_detector_imagen_congelada_marca_desconexion_tras_30s(self):
        import numpy as np

        camara = self.modulo.CamaraStream(0)
        frame_a = np.zeros((20, 20, 3), dtype=np.uint8)
        frame_b = np.full((20, 20, 3), 25, dtype=np.uint8)

        self.assertFalse(camara._detectar_frame_congelado(frame_a, 0.0))
        self.assertFalse(camara._detectar_frame_congelado(frame_a, 29.0))
        self.assertFalse(camara._detectar_frame_congelado(frame_b, 29.5))
        self.assertFalse(camara._detectar_frame_congelado(frame_b, 59.0))
        self.assertTrue(camara._detectar_frame_congelado(frame_b, 60.0))

    def test_desconexion_camara_cierra_tracks_perdidos_y_no_encola_snapshots_obsoletos(self):
        import numpy as np

        import main
        from modulos.comportamiento import GestorComportamiento, TipoEvento
        from modulos.vision_supervision import AveEnFrame, ResultadoVision

        frame_valido = np.zeros((120, 160, 3), dtype=np.uint8)
        lecturas = iter(
            [
                (1, frame_valido),
                (2, frame_valido),
                (1, None),
            ]
        )
        estados = iter(
            [
                {"conectada": True, "ultimo_error": None, "reintentos": 0},
                {"conectada": True, "ultimo_error": None, "reintentos": 0},
                {
                    "conectada": False,
                    "ultimo_error": "se perdió la señal",
                    "reintentos": 1,
                },
            ]
        )
        tiempo_actual = [0.0]
        ciclos_waitkey = iter([(1.0, 0), (5.0, 0), (5.0, ord("q"))])
        snapshots_debidos = iter([False, False, True])

        def esperar_tecla(_ms):
            siguiente_ts, tecla = next(ciclos_waitkey)
            tiempo_actual[0] = siguiente_ts
            return tecla

        eventos_registrados = []
        hud_acciones = []
        tracks_al_desconectar = {}
        gestores_creados = []

        class CamaraFalsa:
            def __init__(self, _fuente):
                pass

            def start(self):
                pass

            def stop(self):
                pass

            def leer(self):
                return next(lecturas)

            def estado(self):
                return next(estados)

        class ProcesadorFalso:
            def __init__(self, **_kwargs):
                self._pendiente = None

            def enviar_frame_async(self, frame, frame_id, _fn):
                self._pendiente = (["ok"], True, frame, frame_id)

            def recoger_resultado_async(self):
                paquete = self._pendiente
                self._pendiente = None
                return paquete

            def procesar(self, _res, _frame, _id, _mov):
                return ResultadoVision(
                    detecciones=[1],
                    aves=[1],
                    comederos=[],
                    bebederos=[],
                    etiquetas=["ninfa #1 0.90"],
                    aves_info=[AveEnFrame((10, 10, 50, 50), 0.9, 1, None, None)],
                )

            def detener_worker_async(self):
                pass

        class VisualizadorFalso:
            def anotar(self, canvas, _vision, *_args, **_kwargs):
                return canvas

        class ZonasFalsas:
            def actualizar(self, *_args, **_kwargs):
                pass

            def evaluar(self, _aves):
                return [False], [False]

            def anotar(self, canvas):
                return canvas

        class MovimientoFalso:
            def get_activity_level(self, _tid):
                return "Normal", 10.0

            def get_global_activity(self):
                return "Normal", 10.0

        class SnapshotFalso:
            def toca_guardar(self):
                return next(snapshots_debidos)

            def armar_filas(self, *_args):
                return [("Snapshot", "Estado", 1.0, "Normal", 1.0, "obsoleto")]

        class GestorEspia(GestorComportamiento):
            def __init__(self):
                super().__init__()
                gestores_creados.append(self)

            def actualizar(self, observaciones, ahora):
                eventos = super().actualizar(observaciones, ahora)
                eventos_registrados.extend(eventos)
                return eventos

        def registrar_hud(_canvas, accion, *_args, **_kwargs):
            hud_acciones.append(accion)
            if accion == "CAMARA DESCONECTADA" and gestores_creados:
                tracks_al_desconectar["tracks"] = dict(gestores_creados[0].tracks)

        class ModeloFalso:
            names = {0: "bebedero", 1: "comedero", 2: "ninfa"}

        class IdentificadorFalso:
            pass

        with ExitStack() as stack:
            for args, kwargs in (
                ((main, "DB_ACTIVA", False), {}),
                ((main, "cargar_modelo"), {"return_value": ModeloFalso()}),
                ((main, "seleccionar_fuente_video"), {"return_value": (0, None)}),
                (
                    (main, "configurar_identificacion"),
                    {"return_value": (IdentificadorFalso(), ["Yukki"])},
                ),
                ((main, "CamaraStream", CamaraFalsa), {}),
                ((main, "ProcesadorDetecciones", ProcesadorFalso), {}),
                ((main, "VisualizadorDetecciones", VisualizadorFalso), {}),
                ((main, "GestorZonas", ZonasFalsas), {}),
                ((main, "MovementMonitor", MovimientoFalso), {}),
                ((main, "SnapshotPeriodico", SnapshotFalso), {}),
                ((main, "GestorComportamiento", GestorEspia), {}),
                ((main, "es_modo_headless"), {"return_value": False}),
                ((main, "dibujar_hud"), {"side_effect": registrar_hud}),
                ((main, "guardar_async"), {}),
                ((main.cv2, "imshow"), {}),
                ((main.cv2, "destroyAllWindows"), {}),
                ((main.cv2, "waitKey"), {"side_effect": esperar_tecla}),
                (
                    (main.time, "monotonic"),
                    {"side_effect": lambda: tiempo_actual[0]},
                ),
                ((main.time, "time"), {"side_effect": lambda: tiempo_actual[0]}),
                ((main.time, "sleep"), {}),
            ):
                stack.enter_context(patch.object(*args, **kwargs))
            mock_guardar_filas = stack.enter_context(
                patch.object(main, "guardar_filas_async")
            )
            main.iniciar_monitoreo()

        self.assertEqual({}, tracks_al_desconectar.get("tracks"))
        self.assertIn("CAMARA DESCONECTADA", hud_acciones)
        self.assertTrue(
            any(
                e.tipo == TipoEvento.FIN and e.motivo == "track_perdido"
                for e in eventos_registrados
            )
        )
        mock_guardar_filas.assert_not_called()


if __name__ == "__main__":
    unittest.main()
