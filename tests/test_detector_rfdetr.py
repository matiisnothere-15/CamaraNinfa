import builtins
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import supervision as sv

import main
from modulos import detector_rfdetr as modulo_detector
from modulos.detector_rfdetr import ROBOFLOW_MODEL_ID_DEFAULT, DetectorRFDETR
from modulos.movement_analysis import MovementMonitor
from modulos.vision_supervision import ProcesadorDetecciones

RAIZ = Path(__file__).resolve().parent.parent


class _IdentificadorStub:
    def votar(self, _track_id, _frame, _coords):
        return None

    def resolver(self, _tracks):
        return {}


class DetectorRFDETRTests(unittest.TestCase):
    def test_proveedores_onnx_usan_cuda_solo_si_esta_disponible(self):
        ort = types.SimpleNamespace(
            get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        with (
            patch.dict(sys.modules, {"onnxruntime": ort}),
            patch.object(modulo_detector.torch.cuda, "is_available", return_value=True),
        ):
            self.assertEqual(
                ["CUDAExecutionProvider", "CPUExecutionProvider"],
                modulo_detector._proveedores_onnx(),
            )

    def test_proveedores_onnx_no_solicitan_cuda_ni_coreml_inexistentes(self):
        ort = types.SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            self.assertEqual(["CPUExecutionProvider"], modulo_detector._proveedores_onnx())

    def test_pesos_relativos_se_resuelven_desde_el_proyecto(self):
        motor = types.SimpleNamespace(RFDETRBase=Mock())
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, {"rfdetr": motor}),
            patch.object(Path, "is_file", return_value=True),
        ):
            DetectorRFDETR(weights_path="pesos/modelo.pth")
        motor.RFDETRBase.assert_called_once_with(
            pretrain_weights=str(RAIZ / "pesos" / "modelo.pth")
        )

    def test_backend_usa_modelo_nas_y_cache_local_sin_enviar_frames(self):
        motor = Mock()
        motor.get_model.return_value = Mock()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, {"inference": motor}),
            patch.object(modulo_detector, "_proveedores_onnx", return_value=["CPUExecutionProvider"]),
        ):
            detector = DetectorRFDETR(api_key="clave-de-prueba")
            cache = os.environ.get("MODEL_CACHE_DIR")
        motor.get_model.assert_called_once_with(
            model_id=ROBOFLOW_MODEL_ID_DEFAULT,
            api_key="clave-de-prueba",
            onnxruntime_execution_providers=["CPUExecutionProvider"],
        )
        self.assertEqual(str(RAIZ / ".cache" / "roboflow"), cache)
        detector._modelo_inference.infer.assert_not_called()

    def test_main_selecciona_rfdetr_por_defecto_y_desactiva_yolo(self):
        entorno = {k: v for k, v in os.environ.items() if k != "NINFAS_DETECTOR"}
        with (
            patch.dict(os.environ, entorno, clear=True),
            patch.object(DetectorRFDETR, "_cargar_backend", return_value=None),
            patch.object(main, "YOLO") as mock_yolo,
        ):
            self.assertEqual("rfdetr", main.detector_configurado())
            modelo = main.cargar_modelo()

        self.assertIsInstance(modelo, DetectorRFDETR)
        self.assertEqual(ROBOFLOW_MODEL_ID_DEFAULT, modelo.model_id)
        self.assertEqual({0: "bebedero", 1: "comedero", 2: "ninfa"}, modelo.names)
        mock_yolo.assert_not_called()

    def test_rfdetr_track_convierte_roboflow_a_xyxy_y_asigna_track_id_con_botsort(self):
        desplazamiento = [0.0]

        def predictor_roboflow(_frame, _conf):
            dx = desplazamiento[0]
            return [
                types.SimpleNamespace(
                    predictions=[
                        types.SimpleNamespace(
                            x=300.0 + dx,
                            y=220.0,
                            width=100.0,
                            height=120.0,
                            confidence=0.93,
                            class_name="ninfa",
                        ),
                        types.SimpleNamespace(
                            x=120.0,
                            y=360.0,
                            width=90.0,
                            height=80.0,
                            confidence=0.88,
                            class_name="Comedero",
                        ),
                        types.SimpleNamespace(
                            x=500.0,
                            y=360.0,
                            width=80.0,
                            height=90.0,
                            confidence=0.91,
                            class_name="bebedero",
                        ),
                    ]
                )
            ]

        detector = DetectorRFDETR(
            tracker_config=RAIZ / "botsort_ninfas.yaml",
            predictor=predictor_roboflow,
        )
        procesador = ProcesadorDetecciones(
            nombres_clases=detector.names,
            confianza_ninfa=0.55,
            confianza_platos=0.55,
        )
        movimiento = MovementMonitor()
        identificador = _IdentificadorStub()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        res1 = detector.track(
            frame, persist=True, conf=0.55, tracker=RAIZ / "botsort_ninfas.yaml"
        )
        vis1 = procesador.procesar(res1, frame, identificador, movimiento)

        self.assertEqual(1, len(vis1.aves))
        self.assertEqual(1, len(vis1.comederos))
        self.assertEqual(1, len(vis1.bebederos))
        self.assertIsNotNone(vis1.aves_info[0].track_id)
        self.assertEqual((250, 160, 350, 280), vis1.aves_info[0].coords)
        track_id_1 = vis1.aves_info[0].track_id

        desplazamiento[0] = 6.0
        res2 = detector.track(
            frame, persist=True, conf=0.55, tracker=RAIZ / "botsort_ninfas.yaml"
        )
        vis2 = procesador.procesar(res2, frame, identificador, movimiento)

        self.assertEqual(1, len(vis2.aves))
        self.assertEqual(track_id_1, vis2.aves_info[0].track_id)
        # BoT-SORT aplica filtro de Kalman sobre la caja rastreada
        self.assertGreater(vis2.aves_info[0].coords[0], vis1.aves_info[0].coords[0])
        self.assertLessEqual(vis2.aves_info[0].coords[0], 256)

        pred2 = detector.predict(frame, conf=0.55)
        self.assertEqual(
            [256, 160, 356, 280],
            pred2[0].boxes.xyxy[0].round().int().tolist(),
        )

    def test_rfdetr_soporta_sv_detections_y_predict_sin_tracker(self):
        def predictor_sv(_frame, _conf):
            return sv.Detections(
                xyxy=np.array(
                    [
                        [100.0, 100.0, 200.0, 220.0],
                        [300.0, 300.0, 360.0, 360.0],
                    ],
                    dtype=np.float32,
                ),
                confidence=np.array([0.85, 0.30], dtype=np.float32),
                class_id=np.array([2, 1], dtype=int),
                data={"class_name": np.array(["ninfa", "comedero"])},
            )

        detector = DetectorRFDETR(predictor=predictor_sv)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        resultados = detector.predict(frame, conf=0.55)

        self.assertEqual(1, len(resultados))
        det = sv.Detections.from_ultralytics(resultados[0])
        self.assertEqual(1, len(det))
        self.assertIsNone(det.tracker_id)
        self.assertEqual([2], det.class_id.tolist())

    def test_error_claro_si_falta_inference(self):
        import_real = builtins.__import__

        def importar_sin_inference(nombre, *args, **kwargs):
            if nombre == "inference":
                raise ImportError("No module named 'inference'")
            return import_real(nombre, *args, **kwargs)

        with (
            patch.dict(os.environ, {"RFDETR_WEIGHTS_PATH": ""}, clear=False),
            patch.object(builtins, "__import__", side_effect=importar_sin_inference),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                DetectorRFDETR()
        self.assertIn("inference-gpu", str(ctx.exception))
        self.assertIn("ROBOFLOW_API_KEY", str(ctx.exception))

    def test_rfdetr_soporta_json_anidado_de_roboflow_workflows(self):
        respuesta_workflow = [
            {
                "predictions": {
                    "image": {"width": 994, "height": 556},
                    "predictions": [
                        {
                            "width": 198,
                            "height": 292,
                            "x": 599,
                            "y": 276,
                            "confidence": 0.91804039478302,
                            "class_id": 2,
                            "class": "ninfa",
                            "detection_id": "59548d15-9114-4a4e-bb86-0dc5a81e7049",
                            "parent_id": "image",
                        }
                    ],
                }
            }
        ]
        detector = DetectorRFDETR(predictor=lambda _frame, _conf: respuesta_workflow)
        frame = np.zeros((556, 994, 3), dtype=np.uint8)
        resultados = detector.predict(frame, conf=0.55)

        self.assertEqual(1, len(resultados))
        boxes = resultados[0].boxes
        self.assertEqual([500, 130, 698, 422], boxes.xyxy[0].round().int().tolist())
        self.assertEqual([2], boxes.cls.int().tolist())
        self.assertAlmostEqual(0.91804039478302, float(boxes.conf[0]), places=5)


if __name__ == "__main__":
    unittest.main()
