import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import modulos.base_datos as base_datos
from modulos.base_datos import (
    ColaEscrituraBD,
    contar_lotes_respaldo,
    dividir_batches_sql,
    normalizar_filas,
)


class ConexionFalsa:
    def __init__(self):
        self.sentencias = []
        self.commits = 0

    def cursor(self):
        return self

    def execute(self, query, params=()):
        self.sentencias.append((query, params))

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class ConexionAzureTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "server": "sql.example.test",
            "database": "aves",
            "username": "lector",
            "password": "clave_ficticia",
            "driver": "ODBC Driver 18 for SQL Server",
        }

    def test_conexion_normaliza_tcp_puerto_y_llaves_del_driver(self):
        servidores = (
            ("sql.example.test", "tcp:sql.example.test,1433"),
            ("tcp:sql.example.test", "tcp:sql.example.test,1433"),
            ("sql.example.test,1433", "tcp:sql.example.test,1433"),
            ("tcp:sql.example.test,1433", "tcp:sql.example.test,1433"),
            ("TCP:sql.example.test,1444", "tcp:sql.example.test,1444"),
            ("sql.example.test:1444", "tcp:sql.example.test,1444"),
        )
        for servidor, esperado in servidores:
            for driver in ("ODBC Driver 18 for SQL Server", "{ODBC Driver 18 for SQL Server}"):
                with self.subTest(servidor=servidor, driver=driver):
                    llamadas = []
                    conexion = object()

                    def conectar(cadena, *, _llamadas=llamadas, _conexion=conexion, **opciones):
                        _llamadas.append((cadena, opciones))
                        return _conexion

                    config = dict(self.config, server=servidor, driver=driver)
                    with (
                        patch.object(base_datos, "_cargar_config_azure", return_value=config),
                        patch.object(base_datos, "pyodbc", SimpleNamespace(connect=conectar)),
                    ):
                        self.assertIs(conexion, base_datos._crear_conexion())

                    self.assertEqual(
                        [
                            (
                                "DRIVER={ODBC Driver 18 for SQL Server};"
                                f"SERVER={{{esperado}}};DATABASE={{aves}};"
                                "UID={lector};PWD={clave_ficticia};"
                                "Encrypt=yes;TrustServerCertificate=no;",
                                {"timeout": 30},
                            )
                        ],
                        llamadas,
                    )

    def test_conexion_escapa_delimitadores_odbc_y_preserva_espacios(self):
        for clave, escapada in (
            ("a;b}c", "{a;b}}c}"),
            ("{abc}", "{{abc}}}"),
            (" espacios ", "{ espacios }"),
        ):
            with self.subTest(clave=clave):
                llamadas = []
                config = dict(self.config, database="aves;qa}", username="lector;}", password=clave)
                driver = SimpleNamespace(
                    connect=lambda cadena, _llamadas=llamadas, **_: _llamadas.append(cadena)
                )
                with (
                    patch.object(base_datos, "_cargar_config_azure", return_value=config),
                    patch.object(base_datos, "pyodbc", driver),
                ):
                    base_datos._crear_conexion()

                self.assertIn("DATABASE={aves;qa}}};UID={lector;}}};", llamadas[0])
                self.assertIn(f"PWD={escapada};Encrypt=yes;", llamadas[0])

    def test_configuracion_con_prefijo_o_puerto_duplicado_no_conecta(self):
        for servidor in ("tcp:tcp:sql.example.test,1433", "sql.example.test,1433,1433"):
            with self.subTest(servidor=servidor):
                llamadas = []
                config = dict(self.config, server=servidor)
                driver = SimpleNamespace(
                    connect=lambda *args, _llamadas=llamadas, **kw: _llamadas.append(args)
                )
                with (
                    patch.object(base_datos, "_cargar_config_azure", return_value=config),
                    patch.object(base_datos, "pyodbc", driver),
                    redirect_stdout(StringIO()),
                ):
                    self.assertIsNone(base_datos._crear_conexion())

                self.assertEqual([], llamadas)

    def test_error_de_conexion_no_imprime_credenciales(self):
        def conectar(*args, **kwargs):
            raise RuntimeError("08001", f"Error ficticio: PWD={self.config['password']}")

        salida = StringIO()
        with (
            patch.object(base_datos, "_cargar_config_azure", return_value=self.config),
            patch.object(base_datos, "pyodbc", SimpleNamespace(connect=conectar)),
            redirect_stdout(salida),
        ):
            self.assertIsNone(base_datos._crear_conexion())

        self.assertIn("08001", salida.getvalue())
        self.assertNotIn(self.config["password"], salida.getvalue())


class BaseDatosTests(unittest.TestCase):
    def test_divide_batches_go_solo_en_linea_independiente(self):
        sql = "SELECT 'go';\nGO\nSELECT 2;\n go \nSELECT 3;"
        self.assertEqual(
            ["SELECT 'go';", "SELECT 2;", "SELECT 3;"],
            dividir_batches_sql(sql),
        )

    def test_normaliza_registro_heredado_a_ocho_columnas(self):
        self.assertEqual(
            [("A", "B", 1, "C", 0.5, "N", None, None)],
            normalizar_filas([("A", "B", 1, "C", 0.5, "N")]),
        )

    def test_rechaza_registros_con_forma_invalida(self):
        with self.assertRaises(ValueError):
            normalizar_filas([("A", "B")])
        with self.assertRaises(ValueError):
            normalizar_filas([tuple(range(9))])

    def test_cola_preserva_orden_y_vacia_antes_de_cerrar(self):
        recibidos = []
        cola = ColaEscrituraBD(lambda filas: recibidos.extend(filas)).start()
        cola.encolar([("A", "primero", 1, "ok", 1, "")])
        cola.encolar([("A", "segundo", 2, "ok", 1, "")])
        cola.stop()

        self.assertEqual(["primero", "segundo"], [fila[1] for fila in recibidos])

    def test_transaccion_confirma_una_sola_vez(self):
        conexion = ConexionFalsa()
        with patch.object(base_datos, "_conexion", conexion):
            base_datos.ejecutar_transaccion(
                [("UPDATE Uno SET x = ?", (1,)), ("DELETE FROM Dos", ())]
            )

        self.assertEqual(2, len(conexion.sentencias))
        self.assertEqual(1, conexion.commits)

    def test_cola_guarda_en_respaldo_local_ante_fallo_y_reintenta_al_recuperar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_spool = Path(tmpdir) / "pendientes.jsonl"
            recibidos = []
            fallar = True
            t_fallo = datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone.utc)
            t_recuperacion = datetime(2026, 7, 12, 10, 5, 0, tzinfo=timezone.utc)
            reloj = [t_fallo]

            class DatetimeSimulado(datetime):
                @classmethod
                def now(cls, tz=None):
                    return reloj[0]

            def insertador_simulado(filas):
                if fallar:
                    return False
                recibidos.extend(filas)
                return True

            with patch.object(base_datos, "datetime", DatetimeSimulado):
                cola = ColaEscrituraBD(
                    insertador=insertador_simulado,
                    ruta_respaldo=ruta_spool,
                ).start()
                cola.encolar([("Accion", "lote_caido", 1.0, "Inicio", 0.9, "")])
                cola._cola.join()

                self.assertTrue(ruta_spool.is_file())
                self.assertEqual(1, contar_lotes_respaldo(ruta_spool))
                self.assertEqual([], recibidos)

                fallar = False
                reloj[0] = t_recuperacion
                cola.encolar([("Accion", "lote_recuperado", 2.0, "Fin", 0.9, "")])
                cola.stop()

            self.assertFalse(ruta_spool.exists())
            self.assertEqual(0, contar_lotes_respaldo(ruta_spool))
            self.assertEqual(
                ["lote_caido", "lote_recuperado"],
                [fila[1] for fila in recibidos],
            )
            self.assertEqual(t_fallo.isoformat(), recibidos[0][8])
            self.assertEqual(t_recuperacion.isoformat(), recibidos[1][8])

            filas_insert = base_datos._preparar_filas_insert(recibidos)
            self.assertEqual(t_fallo.replace(tzinfo=None), filas_insert[0][0])
            self.assertEqual(t_recuperacion.replace(tzinfo=None), filas_insert[1][0])

    def test_reintento_conserva_linea_corrupta_y_lotes_posteriores_en_orden(self):
        primero = [["Accion", "primero", 1, "Inicio", 0.9, "", None, None]]
        segundo = [["Accion", "segundo", 2, "Inicio", 0.9, "", None, None]]
        for corrupta in (b"{json incompleto\n", b'[{"fila": "invalida"}]\n'):
            with self.subTest(corrupta=corrupta), tempfile.TemporaryDirectory() as tmpdir:
                ruta = Path(tmpdir) / "pendientes.jsonl"
                pendiente = corrupta + json.dumps(segundo).encode() + b"\n"
                ruta.write_bytes(json.dumps(primero).encode() + b"\n" + pendiente)
                recibidos = []
                cola = ColaEscrituraBD(recibidos.extend, ruta_respaldo=ruta)

                self.assertFalse(cola._reintentar_respaldo())

                self.assertEqual(["primero"], [fila[1] for fila in recibidos])
                self.assertEqual(pendiente, ruta.read_bytes())
                self.assertFalse(cola._reintentar_respaldo())
                self.assertEqual(["primero"], [fila[1] for fila in recibidos])
                self.assertEqual(pendiente, ruta.read_bytes())

                ruta.write_bytes(json.dumps(segundo).encode() + b"\n")
                self.assertTrue(cola._reintentar_respaldo())
                self.assertEqual(["primero", "segundo"], [fila[1] for fila in recibidos])
                self.assertFalse(ruta.exists())

    def test_cola_agrega_nuevos_lotes_sin_descartar_respaldo_corrupto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = Path(tmpdir) / "pendientes.jsonl"
            segundo = [["Accion", "segundo", 2, "Inicio", 0.9, "", None, None]]
            pendiente = b"{json incompleto\n" + json.dumps(segundo).encode()
            ruta.write_bytes(pendiente)
            recibidos = []
            cola = ColaEscrituraBD(recibidos.extend, ruta_respaldo=ruta)

            cola.encolar([("Accion", "tercero", 3, "Inicio", 0.9, "")])
            cola.stop()

            self.assertEqual([], recibidos)
            contenido = ruta.read_bytes()
            self.assertTrue(contenido.startswith(pendiente + b"\n"))
            lineas = contenido.splitlines()
            self.assertEqual(3, len(lineas))
            self.assertEqual("segundo", json.loads(lineas[1])[0][1])
            self.assertEqual("tercero", json.loads(lineas[2])[0][1])


if __name__ == "__main__":
    unittest.main()
