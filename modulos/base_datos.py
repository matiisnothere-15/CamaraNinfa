"""Persistencia centralizada para Azure SQL.

Todas las lecturas y escrituras comparten el mismo ``RLock`` porque pyodbc no
permite ejecutar operaciones concurrentes sobre una única conexión. El monitor
usa :class:`ColaEscrituraBD` para no bloquear el procesamiento de video.
"""

from __future__ import annotations

import os
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:
    import pyodbc
except ImportError:  # Permite ejecutar las pruebas que no requieren Azure SQL.
    pyodbc = None


class ErrorBaseDatos(RuntimeError):
    """Error estable que la API puede convertir en una respuesta HTTP 503."""


_conexion = None
_lock = threading.RLock()


def _cargar_config_azure() -> dict:
    """Carga credenciales desde el entorno o desde la configuración heredada."""
    config = {
        "server": os.getenv("AZURE_SERVER"),
        "database": os.getenv("AZURE_DATABASE"),
        "username": os.getenv("AZURE_USERNAME"),
        "password": os.getenv("AZURE_PASSWORD"),
        "driver": os.getenv("AZURE_DRIVER", "{ODBC Driver 18 for SQL Server}"),
    }
    if all(config[clave] for clave in ("server", "database", "username", "password")):
        return config

    try:
        from config.credenciales import AZURE_CONFIG  # type: ignore

        return dict(AZURE_CONFIG)
    except Exception:
        return {}


def _crear_conexion():
    config = _cargar_config_azure()
    if not config or pyodbc is None:
        return None

    cadena = (
        f"DRIVER={config['driver']};"
        f"SERVER={config['server']};PORT=1433;"
        f"DATABASE={config['database']};"
        f"UID={config['username']};PWD={config['password']};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    try:
        return pyodbc.connect(cadena)
    except Exception as error:
        print(f"No fue posible conectar con Azure SQL: {error}")
        return None


def obtener_conexion():
    """Devuelve la conexión compartida, creándola cuando sea necesario."""
    global _conexion
    with _lock:
        if _conexion is None:
            _conexion = _crear_conexion()
        return _conexion


def _descartar_conexion() -> None:
    global _conexion
    with _lock:
        if _conexion is not None:
            try:
                _conexion.close()
            except Exception:
                pass
        _conexion = None


def _rollback(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def _con_reintento(operacion: Callable):
    """Ejecuta una operación bloqueada y reabre una conexión muerta una vez."""
    ultimo_error: Exception | None = None
    with _lock:
        for _intento in range(2):
            conn = obtener_conexion()
            if conn is None:
                raise ErrorBaseDatos("Azure SQL no está configurado o no está disponible.")
            try:
                return operacion(conn)
            except Exception as error:
                ultimo_error = error
                _rollback(conn)
                _descartar_conexion()
    raise ErrorBaseDatos(f"Falló la operación en Azure SQL: {ultimo_error}") from ultimo_error


def consultar(query: str, params: Sequence = ()) -> list[dict]:
    """Ejecuta un SELECT y retorna filas indexadas por nombre de columna."""

    def operacion(conn):
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        columnas = [columna[0] for columna in cursor.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cursor.fetchall()]

    return _con_reintento(operacion)


def ejecutar(query: str, params: Sequence = ()) -> None:
    """Ejecuta una sentencia y confirma la transacción."""

    def operacion(conn):
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        conn.commit()

    _con_reintento(operacion)


def ejecutar_transaccion(sentencias: Iterable[tuple[str, Sequence]]) -> None:
    """Ejecuta varias sentencias de forma atómica con un único commit."""
    sentencias = list(sentencias)
    if not sentencias:
        return

    def operacion(conn):
        cursor = conn.cursor()
        for query, params in sentencias:
            cursor.execute(query, tuple(params))
        conn.commit()

    _con_reintento(operacion)


QUERY_INSERT = """
    INSERT INTO BitacoraAves
    (Categoria, Accion, Valor_Numerico, Estado_Observado, Confianza_IA, Notas, AveId, TrackId)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def normalizar_filas(filas: Iterable[Sequence]) -> list[tuple]:
    """Convierte registros heredados de seis columnas al esquema de ocho."""
    resultado = []
    for fila in filas:
        fila = tuple(fila)
        if not 6 <= len(fila) <= 8:
            raise ValueError("Cada registro debe contener entre 6 y 8 valores.")
        resultado.append(fila + (None,) * (8 - len(fila)))
    return resultado


def insertar_registros(filas: Iterable[Sequence]) -> bool:
    """Inserta un lote completo en una sola transacción."""
    filas = normalizar_filas(filas)
    if not filas:
        return True

    try:
        def operacion(conn):
            cursor = conn.cursor()
            cursor.executemany(QUERY_INSERT, filas)
            conn.commit()

        _con_reintento(operacion)
        return True
    except ErrorBaseDatos as error:
        print(f"No se pudieron guardar {len(filas)} registros: {error}")
        return False


def insertar_registro(
    categoria,
    accion,
    valor,
    estado,
    confianza,
    notas="",
    ave_id=None,
    track_id=None,
) -> bool:
    return insertar_registros(
        [(categoria, accion, valor, estado, confianza, notas, ave_id, track_id)]
    )


def obtener_aves() -> list[dict]:
    """Retorna las aves registradas; conserva el contrato anterior."""
    try:
        filas = consultar("SELECT Id, Nombre, Color, Notas FROM Aves ORDER BY Id")
    except ErrorBaseDatos as error:
        print(f"No se pudieron leer las aves: {error}")
        return []
    return [
        {
            "id": fila["Id"],
            "nombre": fila["Nombre"],
            "color": fila["Color"],
            "notas": fila["Notas"],
        }
        for fila in filas
    ]


def _a_timestamp_utc(valor) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.timestamp()
    return None


def obtener_estado_salud_inicial() -> dict[str, dict[str, float]]:
    """Recupera la última alimentación e hidratación de cada ave."""
    try:
        filas = consultar(
            """
            SELECT a.Nombre, b.Accion, MAX(b.Fecha) AS UltimaFecha
            FROM Aves a
            INNER JOIN BitacoraAves b ON b.AveId = a.Id
            WHERE b.Categoria IN ('Accion', 'Comportamiento')
              AND b.Accion IN ('Alimentacion', 'Hidratacion')
              AND b.Estado_Observado IN ('Inicio', 'Fin', 'Activo')
            GROUP BY a.Nombre, b.Accion
            """
        )
    except ErrorBaseDatos as error:
        print(f"No se pudo restaurar el estado de salud: {error}")
        return {}

    estado: dict[str, dict[str, float]] = {}
    for fila in filas:
        timestamp = _a_timestamp_utc(fila["UltimaFecha"])
        if timestamp is None:
            continue
        clave = "comer" if fila["Accion"] == "Alimentacion" else "beber"
        estado.setdefault(fila["Nombre"], {})[clave] = timestamp
    return estado


class ColaEscrituraBD:
    """Un único escritor FIFO para desacoplar Azure SQL del bucle de video."""

    _SENTINELA = object()

    def __init__(self, insertador: Callable = insertar_registros):
        self._insertador = insertador
        self._cola: queue.Queue = queue.Queue()
        self._hilo: threading.Thread | None = None
        self._cerrada = False

    def start(self) -> "ColaEscrituraBD":
        if self._hilo is None:
            self._hilo = threading.Thread(
                target=self._procesar,
                name="azure-sql-writer",
                daemon=True,
            )
            self._hilo.start()
        return self

    def encolar(self, filas: Iterable[Sequence]) -> bool:
        filas = normalizar_filas(filas)
        if not filas or self._cerrada:
            return False
        self.start()
        self._cola.put(filas)
        return True

    def _procesar(self) -> None:
        while True:
            trabajo = self._cola.get()
            try:
                if trabajo is self._SENTINELA:
                    return
                self._insertador(trabajo)
            except Exception as error:
                print(f"Error en la cola de Azure SQL: {error}")
            finally:
                self._cola.task_done()

    def stop(self) -> None:
        """Espera los registros pendientes y detiene limpiamente el escritor."""
        if self._cerrada:
            return
        self._cerrada = True
        if self._hilo is None:
            return
        self._cola.join()
        self._cola.put(self._SENTINELA)
        self._hilo.join(timeout=10)
        self._hilo = None


_cola_escritura: ColaEscrituraBD | None = None


def obtener_cola_escritura() -> ColaEscrituraBD:
    global _cola_escritura
    with _lock:
        if _cola_escritura is None:
            _cola_escritura = ColaEscrituraBD().start()
        return _cola_escritura


def cerrar_cola_escritura() -> None:
    global _cola_escritura
    with _lock:
        cola = _cola_escritura
        _cola_escritura = None
    if cola is not None:
        cola.stop()
    _descartar_conexion()


def dividir_batches_sql(contenido: str) -> list[str]:
    """Separa archivos de SQL Server por líneas GO (no se envían a ODBC)."""
    batches: list[str] = []
    actual: list[str] = []
    for linea in contenido.splitlines():
        if linea.strip().upper() == "GO":
            batch = "\n".join(actual).strip()
            if batch:
                batches.append(batch)
            actual = []
        else:
            actual.append(linea)
    batch = "\n".join(actual).strip()
    if batch:
        batches.append(batch)
    return batches


def aplicar_migraciones(directorio: str | Path) -> list[str]:
    """Aplica, en orden y una sola vez, las migraciones ``*.sql``."""
    archivos = sorted(Path(directorio).glob("*.sql"))

    def operacion(conn):
        cursor = conn.cursor()
        cursor.execute(
            """
            IF OBJECT_ID('dbo.SchemaMigrations', 'U') IS NULL
            CREATE TABLE dbo.SchemaMigrations (
                Nombre NVARCHAR(255) NOT NULL PRIMARY KEY,
                AplicadaEn DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
            )
            """
        )
        conn.commit()
        cursor.execute("SELECT Nombre FROM dbo.SchemaMigrations")
        aplicadas = {fila[0] for fila in cursor.fetchall()}
        nuevas = []
        for archivo in archivos:
            if archivo.name in aplicadas:
                continue
            try:
                for batch in dividir_batches_sql(archivo.read_text(encoding="utf-8")):
                    cursor.execute(batch)
                cursor.execute(
                    "INSERT INTO dbo.SchemaMigrations (Nombre) VALUES (?)",
                    (archivo.name,),
                )
                conn.commit()
                nuevas.append(archivo.name)
            except Exception:
                _rollback(conn)
                raise
        return nuevas

    return _con_reintento(operacion)
