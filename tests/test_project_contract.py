import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent


class ProjectContractTests(unittest.TestCase):
    def test_supervision_esta_fijado(self):
        requirements = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("supervision==0.29.1", requirements)

    def test_env_example_contiene_las_integraciones_sin_secretos(self):
        ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
        pares = {}
        for linea in ejemplo.splitlines():
            limpia = linea.strip()
            if limpia and not limpia.startswith("#") and "=" in limpia:
                clave, valor = limpia.split("=", 1)
                pares[clave.strip()] = valor.strip()

        for variable in (
            "TAPO_USER",
            "CAMARA_RTSP_URL",
            "NINFAS_DETECTOR",
            "ROBOFLOW_MODEL_ID",
            "ROBOFLOW_API_KEY",
            "RFDETR_WEIGHTS_PATH",
            "AZURE_SERVER",
            "FOUNDRY_PROJECT_ENDPOINT",
            "NINFAS_AGENT_API_KEY",
            "NINFAS_ADMIN_API_KEY",
            "NINFAS_ALLOWED_HOSTS",
        ):
            self.assertIn(variable, pares)

        for secreto in (
            "ROBOFLOW_API_KEY",
            "TAPO_PASS",
            "AZURE_PASSWORD",
            "FOUNDRY_API_KEY",
            "NINFAS_AGENT_API_KEY",
            "NINFAS_ADMIN_API_KEY",
            "TELEGRAM_BOT_TOKEN",
        ):
            self.assertEqual("", pares.get(secreto), secreto)

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

    def _diagnosticar_integracion(self, drivers):
        ruta = RAIZ / "tools" / "verificar_proyecto.py"
        spec = importlib.util.spec_from_file_location("verificador_integracion_test", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        entorno_sin_credenciales = {
            "AZURE_SERVER": "",
            "AZURE_DATABASE": "",
            "AZURE_USERNAME": "",
            "AZURE_PASSWORD": "",
            "AZURE_DRIVER": "{ODBC Driver 18 for SQL Server}",
            "FOUNDRY_PROJECT_ENDPOINT": "",
            "FOUNDRY_API_KEY": "",
            "FOUNDRY_MODEL": "",
            "CAMARA_RTSP_URL": "",
            "TAPO_USER": "",
            "TAPO_PASS": "",
            "TAPO_IP": "",
        }
        with (
            patch.dict("os.environ", entorno_sin_credenciales),
            patch("pyodbc.drivers", return_value=drivers),
        ):
            return modulo.verificar_integracion_entorno(probar_conexiones=False)

    def test_verificador_diagnostica_integracion_y_migraciones(self):
        resultado = self._diagnosticar_integracion(["ODBC Driver 18 for SQL Server"])

        self.assertEqual([], resultado["errores"])
        self.assertTrue(any("Driver ODBC disponible" in x for x in resultado["ok"]))
        self.assertTrue(any("Migraciones SQL válidas" in x for x in resultado["ok"]))
        self.assertTrue(any("Azure SQL" in x for x in resultado["pendientes"]))
        self.assertTrue(any("Microsoft Foundry" in x for x in resultado["pendientes"]))

    def test_verificador_diagnostica_falta_de_driver(self):
        resultado = self._diagnosticar_integracion([])

        self.assertEqual(1, len(resultado["errores"]))
        self.assertIn("Falta el driver ODBC", resultado["errores"][0])
        self.assertIn("ODBC Driver 18 for SQL Server", resultado["errores"][0])
        self.assertFalse(any("Driver ODBC disponible" in x for x in resultado["ok"]))
        self.assertTrue(any("Migraciones SQL válidas" in x for x in resultado["ok"]))


if __name__ == "__main__":
    unittest.main()
