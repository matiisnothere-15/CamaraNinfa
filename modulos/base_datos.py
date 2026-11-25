"""Persistencia centralizada para Azure SQL.

Todas las lecturas y escrituras comparten el mismo ``RLock`` porque pyodbc no
permite ejecutar operaciones concurrentes sobre una única conexión. El monitor
usa :class:`ColaEscrituraBD` para no bloquear el procesamiento de video.
"""

from __future__ import annotations

import json
import os
import queue
import re
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


def _escapar_valor_odbc(valor: str) -> str:
    if not isinstance(valor, str) or "\x00" in valor:
        raise ValueError("Valor ODBC inválido.")
    return "{" + valor.replace("}", "}}") + "}"


def _normalizar_servidor_sql(servidor: str) -> str:
    servidor = servidor.strip()
    if servidor[:4].lower() == "tcp:":
        servidor = servidor[4:]
    if "," in servidor:
        host, puerto = servidor.rsplit(",", 1)
    elif ":" in servidor:
        host, puerto = servidor.rsplit(":", 1)
    else:
        host, puerto = servidor, "1433"
    host, puerto = host.strip(), puerto.strip()
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+", host)
        or not re.fullmatch(r"[0-9]+", puerto)
        or not 1 <= int(puerto) <= 65535
    ):
        raise ValueError("Servidor o puerto de Azure SQL inválido.")
    return f"tcp:{host},{int(puerto)}"


def _construir_cadena_conexion(config: dict) -> str:
    driver = config.get("driver", "ODBC Driver 18 for SQL Server").strip()
    if driver.startswith("{") and driver.endswith("}"):
        driver = driver[1:-1].replace("}}", "}")
    atributos = (
        ("DRIVER", driver),
        ("SERVER", _normalizar_servidor_sql(config["server"])),
        ("DATABASE", config["database"]),
        ("UID", config["username"]),
        ("PWD", config["password"]),
    )
    return (
        "".join(f"{clave}={_escapar_valor_odbc(valor)};" for clave, valor in atributos)
        + "Encrypt=yes;TrustServerCertificate=no;"
    )


def _crear_conexion():
    config = _cargar_config_azure()
    if not config or pyodbc is None:
        return None
    try:
        cadena = _construir_cadena_conexion(config)
    except (KeyError, TypeError, ValueError, AttributeError):
        print("Configuración de Azure SQL inválida; revise servidor, driver y credenciales.")
        return None
    try:
        return pyodbc.connect(cadena, timeout=30)
    except Exception as error:
        estado = error.args[0] if error.args else None
        detalle = (
            f" (SQLSTATE {estado})"
            if isinstance(estado, str) and re.fullmatch(r"[A-Z0-9]{5}", estado)
            else ""
        )
        print(f"No fue posible conectar con Azure SQL{detalle}.")
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
    (Fecha, Categoria, Accion, Valor_Numerico, Estado_Observado, Confianza_IA, Notas, AveId, TrackId)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _preparar_filas_insert(filas: Iterable[Sequence]) -> list[tuple]:
    """Normaliza filas y antepone la fecha UTC para insertar en BitacoraAves."""
    preparadas: list[tuple] = []
    for fila in filas:
        tupla = tuple(fila)
        if len(tupla) == 9:
            base = normalizar_filas([tupla[:8]])[0]
            fecha_raw = tupla[8]
            if isinstance(fecha_raw, str):
                fecha = datetime.fromisoformat(fecha_raw)
            elif isinstance(fecha_raw, datetime):
                fecha = fecha_raw
            else:
                fecha = datetime.now(timezone.utc)
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            base = normalizar_filas([tupla])[0]
            fecha = datetime.now(timezone.utc).replace(tzinfo=None)
        preparadas.append((fecha, *base))
    return preparadas


def insertar_registros(filas: Iterable[Sequence]) -> bool:
    """Inserta un lote completo en una sola transacción."""
    filas_insert = _preparar_filas_insert(filas)
    if not filas_insert:
        return True

    try:

        def operacion(conn):
            cursor = conn.cursor()
            cursor.executemany(QUERY_INSERT, filas_insert)
            conn.commit()

        _con_reintento(operacion)
        return True
    except ErrorBaseDatos as error:
        print(f"No se pudieron guardar {len(filas_insert)} registros: {error}")
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


def obtener_estado_salud_inicial() -> dict:
    """Recupera la última alimentación, hidratación y último Snapshot para restaurar salud."""
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
        filas_snapshot = consultar(
            """
            SELECT MAX(Fecha) AS UltimaFecha
            FROM BitacoraAves
            WHERE Categoria = 'Snapshot'
            """
        )
    except ErrorBaseDatos as error:
        print(f"No se pudo restaurar el estado de salud: {error}")
        return {}

    estado: dict = {}
    for fila in filas:
        timestamp = _a_timestamp_utc(fila["UltimaFecha"])
        if timestamp is None:
            continue
        clave = "comer" if fila["Accion"] == "Alimentacion" else "beber"
        estado.setdefault(fila["Nombre"], {})[clave] = timestamp
    if filas_snapshot:
        ts_snapshot = _a_timestamp_utc(filas_snapshot[0].get("UltimaFecha"))
        if ts_snapshot is not None:
            estado["__ultimo_snapshot__"] = ts_snapshot
    return estado


class ColaEscrituraBD:
    """Un único escritor FIFO para desacoplar Azure SQL del bucle de video.

    Si Azure SQL falla temporalmente y ``ruta_respaldo`` está definida, los
    lotes no confirmados se persisten en disco (JSONL) y se reintentan en orden
    FIFO cuando la conexión se restablece.
    """

    _SENTINELA = object()

    def __init__(
        self,
        insertador: Callable = insertar_registros,
        ruta_respaldo: str | Path | None = None,
    ):
        self._insertador = insertador
        self._ruta_respaldo = Path(ruta_respaldo) if ruta_respaldo else None
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
        ahora_utc = datetime.now(timezone.utc).isoformat()
        filas = [fila + (ahora_utc,) for fila in filas]
        self.start()
        self._cola.put(filas)
        return True

    @staticmethod
    def _decodificar_lote_respaldo(linea: bytes) -> list[tuple]:
        datos = json.loads(linea)
        if not isinstance(datos, list) or not datos:
            raise ValueError("El respaldo debe contener un lote no vacío por línea.")
        lote = []
        for fila in datos:
            if not isinstance(fila, list):
                raise ValueError("Cada fila del respaldo debe ser una lista.")
            seq = tuple(fila)
            if len(seq) == 9:
                base = normalizar_filas([seq[:8]])[0]
                lote.append(base + (str(seq[8]),))
            else:
                base = normalizar_filas([seq])[0]
                lote.append(base + (datetime.now(timezone.utc).isoformat(),))
        return lote

    def _guardar_en_respaldo(self, filas: list[tuple]) -> None:
        if self._ruta_respaldo is None or not filas:
            return
        try:
            contenido = json.dumps([list(fila) for fila in filas], ensure_ascii=False)
            with self._ruta_respaldo.open("a+b") as respaldo:
                fin = respaldo.tell()
                if fin:
                    respaldo.seek(-1, 2)
                    if respaldo.read(1) not in {b"\n", b"\r"}:
                        respaldo.write(b"\n")
                respaldo.write(contenido.encode("utf-8") + b"\n")
        except Exception as error:
            print(f"No se pudo escribir el respaldo local de BD: {error}")

    def _reintentar_respaldo(self) -> bool:
        if self._ruta_respaldo is None:
            return True
        try:
            lineas = self._ruta_respaldo.read_bytes().splitlines(keepends=True)
        except FileNotFoundError:
            return True
        except OSError as error:
            print(f"No se pudo leer el respaldo local de BD: {error}")
            return False

        procesadas = 0
        for linea in lineas:
            if not linea.strip():
                procesadas += 1
                continue
            try:
                lote = self._decodificar_lote_respaldo(linea)
            except Exception as error:
                print(f"No se pudo leer el respaldo local de BD: {error}")
                break
            try:
                exito = self._insertador(lote) is not False
            except Exception:
                exito = False
            if not exito:
                break
            procesadas += 1

        restantes = b"".join(lineas[procesadas:])
        if procesadas or not lineas:
            try:
                if restantes:
                    temporal = self._ruta_respaldo.with_name(self._ruta_respaldo.name + ".tmp")
                    temporal.write_bytes(restantes)
                    temporal.replace(self._ruta_respaldo)
                else:
                    self._ruta_respaldo.unlink(missing_ok=True)
            except OSError as error:
                print(f"No se pudo actualizar el respaldo local de BD: {error}")
                return False
        return not restantes

    def _procesar(self) -> None:
        while True:
            trabajo = self._cola.get()
            try:
                if trabajo is self._SENTINELA:
                    return
                if (
                    self._ruta_respaldo is not None
                    and self._ruta_respaldo.is_file()
                    and not self._reintentar_respaldo()
                ):
                    self._guardar_en_respaldo(trabajo)
                    continue
                exito = self._insertador(trabajo) is not False
                if not exito:
                    self._guardar_en_respaldo(trabajo)
            except Exception as error:
                print(f"Error en la cola de Azure SQL: {error}")
                if isinstance(trabajo, list):
                    self._guardar_en_respaldo(trabajo)
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
_RUTA_RESPALDO_PREDETERMINADA = Path(__file__).resolve().parent.parent / "datos_pendientes.jsonl"


def obtener_cola_escritura() -> ColaEscrituraBD:
    global _cola_escritura
    with _lock:
        if _cola_escritura is None:
            _cola_escritura = ColaEscrituraBD(ruta_respaldo=_RUTA_RESPALDO_PREDETERMINADA).start()
        return _cola_escritura


def contar_lotes_respaldo(ruta_respaldo: str | Path | None = None) -> int:
    """Devuelve cuántos lotes pendientes existen en el archivo de respaldo local."""
    ruta = Path(ruta_respaldo) if ruta_respaldo else _RUTA_RESPALDO_PREDETERMINADA
    if not ruta.is_file():
        return 0
    try:
        return sum(1 for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip())
    except Exception:
        return 0


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
