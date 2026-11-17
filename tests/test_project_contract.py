import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


class ProjectContractTests(unittest.TestCase):
    def test_supervision_esta_fijado(self):
        requirements = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("supervision==0.29.1", requirements)

    def test_env_contiene_las_integraciones(self):
        ruta_env = RAIZ / ".env"
        if not ruta_env.is_file():
            self.skipTest(".env no está presente en este entorno")
        ejemplo = ruta_env.read_text(encoding="utf-8")
        for variable in (
            "TAPO_USER",
            "CAMARA_RTSP_URL",
            "AZURE_SERVER",
            "FOUNDRY_PROJECT_ENDPOINT",
            "NINFAS_AGENT_API_KEY",
            "NINFAS_ADMIN_API_KEY",
            "NINFAS_ALLOWED_HOSTS",
        ):
            self.assertIn(f"{variable}=", ejemplo)

    def test_archivos_principales_existen(self):
        for ruta in (
            "main.py",
            "best.pt",
            "LICENSE",
            "app/servidor.py",
            "entrenamiento/data.yaml",
            "tools/orquestador_operativo.ps1",
            "tools/instalar_inicio_automatico.ps1",
        ):
            self.assertTrue((RAIZ / ruta).is_file(), ruta)

    def test_checkpoint_supera_validacion_estatica(self):
        ruta = RAIZ / "tools" / "verificar_proyecto.py"
        spec = importlib.util.spec_from_file_location("verificador_test", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertEqual([], modulo.verificar_modelo())

    def test_no_quedan_utilidades_con_ip_hardcodeada(self):
        for nombre in ("recolector_fotos.py", "escaner_camara.py", "configurar_zonas.py"):
            fuente = (RAIZ / "tools" / nombre).read_text(encoding="utf-8")
            self.assertNotIn("192.168.0.6", fuente)

    def test_verificador_diagnostica_integracion_y_migraciones(self):
        ruta = RAIZ / "tools" / "verificar_proyecto.py"
        spec = importlib.util.spec_from_file_location("verificador_integracion_test", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        entorno_sin_credenciales = {
            "AZURE_SERVER": "",
            "AZURE_DATABASE": "",
            "AZURE_USERNAME": "",
            "AZURE_PASSWORD": "",
            "FOUNDRY_PROJECT_ENDPOINT": "",
            "FOUNDRY_API_KEY": "",
            "FOUNDRY_MODEL": "",
            "CAMARA_RTSP_URL": "",
            "TAPO_USER": "",
            "TAPO_PASS": "",
            "TAPO_IP": "",
        }
        with patch.dict("os.environ", entorno_sin_credenciales):
            resultado = modulo.verificar_integracion_entorno(probar_conexiones=False)

        self.assertEqual([], resultado["errores"])
        self.assertTrue(any("Driver ODBC disponible" in x for x in resultado["ok"]))
        self.assertTrue(any("Migraciones SQL válidas" in x for x in resultado["ok"]))
        self.assertTrue(any("Azure SQL" in x for x in resultado["pendientes"]))
        self.assertTrue(any("Microsoft Foundry" in x for x in resultado["pendientes"]))


if __name__ == "__main__":
    unittest.main()
