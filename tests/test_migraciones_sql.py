import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class MigracionesSqlTests(unittest.TestCase):
    def test_esquema_base_contiene_tablas_y_columnas_requeridas(self):
        sql = (RAIZ / "sql/migrations/001_schema_base.sql").read_text(encoding="utf-8")
        for contrato in (
            "CREATE TABLE dbo.Aves",
            "CREATE TABLE dbo.BitacoraAves",
            "Fecha DATETIME2(3)",
            "AveId INT NULL",
            "TrackId INT NULL",
            "SYSUTCDATETIME()",
        ):
            self.assertIn(contrato, sql)

    def test_upgrade_agrega_integridad_e_indices(self):
        sql = (RAIZ / "sql/migrations/002_upgrade_tracking_indexes.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("ON DELETE SET NULL", sql)
        self.assertIn("IX_BitacoraAves_AveId_Fecha", sql)
        self.assertIn("IX_BitacoraAves_Categoria_Accion_Fecha", sql)
        self.assertIn("DF_Aves_FechaRegistro", sql)

    def test_herramienta_de_migracion_existe(self):
        self.assertTrue((RAIZ / "tools/migrar_bd.py").is_file())


if __name__ == "__main__":
    unittest.main()
