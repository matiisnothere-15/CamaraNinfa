import importlib.util
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class ProjectContractTests(unittest.TestCase):
    def test_supervision_esta_fijado(self):
        requirements = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("supervision==0.29.1", requirements)

    def test_env_example_contiene_las_integraciones(self):
        ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
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
        for ruta in ("main.py", "best.pt", "app/servidor.py", "entrenamiento/data.yaml"):
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


if __name__ == "__main__":
    unittest.main()
