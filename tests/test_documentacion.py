import json
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]


class DocumentacionTests(unittest.TestCase):
    def test_readme_tiene_un_titulo_y_no_conserva_bloques_obsoletos(self):
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        self.assertEqual(1, sum(linea.startswith("# ") for linea in readme.splitlines()))
        for texto_obsoleto in (
            "Píxeles recorridos por minuto",
            "será reemplazada por zonas",
            "CREATE TABLE BitacoraAves",
            "../train/images",
        ):
            self.assertNotIn(texto_obsoleto, readme)

    def test_documentos_principales_existen(self):
        for nombre in (
            "ARQUITECTURA.md",
            "CONFIGURACION_Y_OPERACION.md",
            "ENTRENAMIENTO_Y_EVALUACION.md",
            "ENTREGA_Y_PENDIENTES.md",
            "SEGURIDAD.md",
            "VALIDACION_FINAL_2026-07-12.md",
        ):
            self.assertTrue((RAIZ / "docs" / nombre).is_file(), nombre)

    def test_enlaces_locales_resuelven(self):
        rotos = []
        for documento in DOCUMENTOS:
            texto = documento.read_text(encoding="utf-8")
            for destino in re.findall(r"\[[^]]+\]\(([^)]+)\)", texto):
                if "://" in destino or destino.startswith("#"):
                    continue
                ruta = destino.split("#", 1)[0]
                if ruta and not (documento.parent / ruta).resolve().exists():
                    rotos.append(f"{documento.name}: {destino}")
        self.assertEqual([], rotos)

    def test_bloques_de_codigo_estan_cerrados(self):
        for documento in DOCUMENTOS:
            texto = documento.read_text(encoding="utf-8")
            self.assertEqual(0, texto.count("```") % 2, documento.name)

    def test_documentacion_del_dataset_coincide_con_reporte(self):
        reporte = json.loads(
            (RAIZ / "entrenamiento/dataset_report.json").read_text(encoding="utf-8")
        )
        guia = (RAIZ / "docs/ENTRENAMIENTO_Y_EVALUACION.md").read_text(
            encoding="utf-8"
        )
        for split, etiqueta in (("train", "Train"), ("val", "Validación"), ("test", "Test")):
            datos = reporte["splits"][split]
            fila = f"| {etiqueta} |"
            self.assertIn(fila, guia)
            self.assertIn(f"| {datos['imagenes']} | {datos['objetos']} |", guia)

    def test_guia_operativa_cubre_variables_publicadas(self):
        ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
        guia = (RAIZ / "docs/CONFIGURACION_Y_OPERACION.md").read_text(
            encoding="utf-8"
        )
        variables = {
            linea.split("=", 1)[0]
            for linea in ejemplo.splitlines()
            if linea and not linea.startswith("#") and "=" in linea
        }
        faltantes = sorted(variable for variable in variables if f"`{variable}`" not in guia)
        self.assertEqual([], faltantes)


if __name__ == "__main__":
    unittest.main()
