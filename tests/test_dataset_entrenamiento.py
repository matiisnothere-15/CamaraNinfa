import hashlib
import json
import unittest
from pathlib import Path

from modulos.dataset_audit import auditar_dataset, leer_data_yaml, resolver_splits
from modulos.metricas_modelo import extraer_metricas_deteccion

RAIZ = Path(__file__).resolve().parent.parent
DATA_YAML = RAIZ / "entrenamiento/data.yaml"


class CajaMetricasFalsa:
    ap_class_index = [0, 1, 2]
    p = [0.8, 0.9, 0.95]
    r = [0.7, 0.85, 0.9]
    f1 = [0.746, 0.874, 0.924]
    ap50 = [0.88, 0.93, 0.97]
    ap = [0.61, 0.72, 0.81]
    mp = 0.883
    mr = 0.817
    map50 = 0.927
    map75 = 0.75
    map = 0.713


class DatasetEntrenamientoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.informe = auditar_dataset(DATA_YAML)

    def test_yaml_resuelve_manifiestos_existentes(self):
        datos = leer_data_yaml(DATA_YAML)
        rutas = resolver_splits(datos)
        self.assertEqual({"train", "val", "test"}, set(rutas))
        self.assertTrue(all(ruta.is_file() for ruta in rutas.values()))

    def test_dataset_no_tiene_errores_ni_fuga_visual_detectada(self):
        self.assertTrue(self.informe["ok"], self.informe["errores"])
        self.assertEqual([], self.informe["errores"])
        self.assertEqual(
            0, self.informe["integridad"]["pares_visualmente_similares"]
        )
        self.assertEqual(178, self.informe["totales"]["imagenes"])

    def test_todas_las_clases_aparecen_en_cada_split(self):
        for split in ("train", "val", "test"):
            self.assertTrue(
                all(valor > 0 for valor in self.informe["splits"][split]["clases"].values())
            )
            self.assertEqual(
                {"polygon": self.informe["splits"][split]["objetos"]},
                self.informe["splits"][split]["formatos"],
            )

    def test_reporte_guardado_corresponde_a_la_huella_actual(self):
        guardado = json.loads(
            (RAIZ / "entrenamiento/dataset_report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(self.informe["huella_sha256"], guardado["huella_sha256"])

    def test_baseline_historico_identifica_checkpoint_y_limitacion(self):
        baseline = json.loads(
            (RAIZ / "entrenamiento/model_baseline.json").read_text(encoding="utf-8")
        )
        digest = hashlib.sha256((RAIZ / "best.pt").read_bytes()).hexdigest()
        self.assertEqual(digest, baseline["checkpoint"]["sha256"])
        self.assertEqual("historico_no_comparable", baseline["estado"])
        self.assertIn("pueden ser optimistas", baseline["limitacion"])

    def test_manifiesto_no_repite_fuentes(self):
        manifiesto = json.loads(
            (RAIZ / "entrenamiento/splits/manifest.json").read_text(encoding="utf-8")
        )
        conjuntos = [
            set(manifiesto["splits"][split]["ids_fuente"])
            for split in ("train", "val", "test")
        ]
        self.assertFalse(conjuntos[0] & conjuntos[1])
        self.assertFalse(conjuntos[0] & conjuntos[2])
        self.assertFalse(conjuntos[1] & conjuntos[2])
        self.assertEqual(138, len(set.union(*conjuntos)))

    def test_metricas_se_exportan_con_contrato_estable(self):
        resultado = extraer_metricas_deteccion(
            CajaMetricasFalsa(), {0: "bebedero", 1: "comedero", 2: "ninfa"}
        )
        self.assertAlmostEqual(0.927, resultado["global"]["map50"])
        self.assertAlmostEqual(0.9, resultado["por_clase"]["ninfa"]["recall"])
        self.assertAlmostEqual(0.72, resultado["por_clase"]["comedero"]["map50_95"])

    def test_scripts_exigen_auditoria_y_separan_test(self):
        entrenar = (RAIZ / "tools/entrenar_modelo.py").read_text(encoding="utf-8")
        evaluar = (RAIZ / "tools/evaluar_modelo.py").read_text(encoding="utf-8")
        self.assertIn("auditar_dataset", entrenar)
        self.assertIn('"deterministic": True', entrenar)
        self.assertIn('default="test"', evaluar)
        self.assertIn("extraer_metricas_deteccion", evaluar)

    def test_evaluacion_test_no_usa_checkpoint_historico_contaminado(self):
        evaluacion = json.loads(
            (RAIZ / "entrenamiento/evaluaciones/best_test_2026-07-12.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotEqual(
            "4cf23872a67b444a02ece450d5af6cb18846ffa5e32c3006ed41d8380000e05b",
            evaluacion["modelo"]["sha256"],
        )
        self.assertEqual("test", evaluacion["dataset"]["split"])
        self.assertEqual(
            self.informe["huella_sha256"], evaluacion["dataset"]["huella_sha256"]
        )
        self.assertEqual(
            "entrenamiento/splits/train.txt", evaluacion["entrenamiento"]["split_train"]
        )
        self.assertEqual(137, evaluacion["entrenamiento"]["imagenes_train"])


if __name__ == "__main__":
    unittest.main()
