import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class SeguridadWebStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = (RAIZ / "app/servidor.py").read_text(encoding="utf-8")
        cls.http = (RAIZ / "app/seguridad_http.py").read_text(encoding="utf-8")
        cls.panel = (RAIZ / "app/static/index.html").read_text(encoding="utf-8")

    def test_api_instala_csp_hosts_y_limites(self):
        self.assertIn("Content-Security-Policy", self.http)
        self.assertIn("TrustedHostMiddleware", self.http)
        self.assertIn("LimitadorSolicitudes", self.http)
        self.assertIn("16_384", self.http)
        self.assertIn("receive_limitado", self.http)

    def test_operaciones_sensibles_exigen_dependencia(self):
        self.assertEqual(4, self.servidor.count("Depends(_proteger_operacion_panel)"))
        self.assertIn("NINFAS_ADMIN_API_KEY", self.servidor)
        self.assertIn("es_direccion_local", self.servidor)

    def test_todas_las_ventanas_horarias_tienen_limites(self):
        self.assertEqual(5, self.servidor.count("ge=1, le=168"))

    def test_panel_no_usa_eventos_inline_y_escapa_datos(self):
        self.assertNotIn("onclick=", self.panel)
        self.assertIn("function esc(valor)", self.panel)
        self.assertIn("${esc(a.nombre)}", self.panel)
        self.assertIn("${esc(r.detalle)}", self.panel)
        self.assertIn("${esc(a.notas || \"\")}", self.panel)
        self.assertNotIn("localStorage.setItem", self.panel)

    def test_panel_centraliza_respuestas_http(self):
        self.assertIn("async function api(", self.panel)
        self.assertNotIn(".then(r => r.json())", self.panel)

    def test_endpoint_healthcheck_existe_y_reporta_monitor_y_respaldo(self):
        self.assertIn('@app.get("/api/health")', self.servidor)
        self.assertIn("monitor_activo", self.servidor)
        self.assertIn("lotes_pendientes_respaldo", self.servidor)

    def test_acciones_y_aves_stats_excluyen_movimiento_e_inactividad(self):
        import re
        import sqlite3
        from datetime import datetime
        from unittest.mock import patch

        import app.servidor as servidor

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE Aves (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Nombre TEXT NOT NULL,
                Color TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE BitacoraAves (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Fecha TEXT NOT NULL DEFAULT (datetime('now')),
                Categoria TEXT NOT NULL,
                Accion TEXT NOT NULL,
                Valor_Numerico REAL,
                Estado_Observado TEXT,
                Confianza REAL,
                Notas TEXT,
                AveId INTEGER,
                TrackId INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO BitacoraAves
                (Categoria, Accion, Valor_Numerico, Estado_Observado, Confianza, Notas, AveId, TrackId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Comportamiento", "Movimiento", 5.0, "Fin", 0.9, "", None, 1),
        )
        conn.execute(
            """
            INSERT INTO BitacoraAves
                (Categoria, Accion, Valor_Numerico, Estado_Observado, Confianza, Notas, AveId, TrackId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("Comportamiento", "Inactividad", 12.0, "Fin", 0.9, "", None, 1),
        )
        conn.commit()

        def consultar_sqlite(query, params=()):
            sql = re.sub(r"TOP\s*\(\s*\d+\s*\)", "", query)
            sql = sql.replace(
                "DATEADD(hour, -?, GETDATE())",
                "datetime('now', '-' || ? || ' hours')",
            )
            filas = []
            for row in conn.execute(sql, params).fetchall():
                item = dict(row)
                if isinstance(item.get("Fecha"), str):
                    item["Fecha"] = datetime.fromisoformat(item["Fecha"])
                filas.append(item)
            return filas

        try:
            with patch.object(servidor, "_consultar", side_effect=consultar_sqlite):
                self.assertEqual([], servidor.acciones(horas=48))
                self.assertEqual(0, servidor.aves_stats(horas=24)["sin_identificar"])

                conn.execute(
                    """
                    INSERT INTO BitacoraAves
                        (Categoria, Accion, Valor_Numerico, Estado_Observado, Confianza, Notas, AveId, TrackId)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("Accion", "Alimentacion", 8.0, "Fin", 0.95, "", None, 2),
                )
                conn.commit()

                resultado_acciones = servidor.acciones(horas=48)
                self.assertEqual(1, len(resultado_acciones))
                self.assertEqual("Alimentacion", resultado_acciones[0]["accion"])
                self.assertEqual(1, servidor.aves_stats(horas=24)["sin_identificar"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
