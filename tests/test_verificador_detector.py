import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "verificador_detector", RAIZ / "tools/verificar_proyecto.py"
)
verificador = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verificador)


class VerificadorDetectorTests(unittest.TestCase):
    def test_detecta_opencv_sin_ventanas_antes_de_abrir_camara(self):
        cv2_falso = SimpleNamespace(getBuildInformation=lambda: "  GUI: NONE\n")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, {"cv2": cv2_falso}),
        ):
            self.assertTrue(verificador.verificar_gui())

    def test_opencv_headless_es_valido_en_modo_headless(self):
        with patch.dict(os.environ, {"NINFAS_HEADLESS": "1"}, clear=True):
            self.assertEqual([], verificador.verificar_gui())

    def test_detecta_motor_inference_ausente_con_rfdetr_predeterminado(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                verificador.importlib.util,
                "find_spec",
                side_effect=lambda nombre: (
                    None if nombre in {"inference", "inference_models"} else object()
                ),
            ),
        ):
            self.assertIn("inference", verificador.verificar_dependencias())

    def test_acepta_inference_models_como_motor_rfdetr_local(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                verificador.importlib.util,
                "find_spec",
                side_effect=lambda nombre: None if nombre == "inference" else object(),
            ),
        ):
            self.assertEqual([], verificador.verificar_dependencias())

    def test_pesos_locales_requieren_rfdetr_en_vez_de_inference(self):
        with (
            patch.dict(os.environ, {"RFDETR_WEIGHTS_PATH": "modelo.pth"}, clear=True),
            patch.object(
                verificador.importlib.util,
                "find_spec",
                side_effect=lambda nombre: None if nombre in {"inference", "rfdetr"} else object(),
            ),
        ):
            self.assertEqual(["rfdetr"], verificador.verificar_dependencias())

    def test_rfdetr_remoto_no_exige_checkpoint_yolo(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(verificador, "RAIZ", Path("directorio-inexistente")),
        ):
            self.assertEqual([], verificador.verificar_modelo())

    def test_pesos_rfdetr_inexistentes_son_bloqueo(self):
        with patch.dict(os.environ, {"RFDETR_WEIGHTS_PATH": "no-existe.pth"}, clear=True):
            errores = verificador.verificar_modelo()
        self.assertTrue(errores)
        self.assertIn("no-existe.pth", errores[0])

    def test_modo_integracion_no_abre_servicios_sin_opcion_explicita(self):
        with (
            patch.object(verificador, "verificar_sintaxis", return_value=[]),
            patch.object(verificador, "verificar_archivos", return_value=[]),
            patch.object(verificador, "verificar_dependencias", return_value=[]),
            patch.object(verificador, "verificar_modelo", return_value=[]),
            patch.object(verificador, "verificar_gui", return_value=[]),
            patch.object(verificador, "verificar_integracion_entorno", return_value={
                "ok": [], "errores": [], "pendientes": []
            }) as diagnosticar,
        ):
            self.assertEqual(0, verificador.main(["--integracion"]))
        diagnosticar.assert_called_once_with(probar_conexiones=False)
