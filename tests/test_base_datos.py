import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
