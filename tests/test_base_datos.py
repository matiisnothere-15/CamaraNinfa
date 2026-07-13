import unittest
from unittest.mock import patch

import modulos.base_datos as base_datos
from modulos.base_datos import ColaEscrituraBD, dividir_batches_sql, normalizar_filas


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


if __name__ == "__main__":
    unittest.main()
