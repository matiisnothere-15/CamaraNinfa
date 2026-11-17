"""API del Monitor de Ninfas.

Lee los datos que el monitor (main.py) guarda en Azure SQL y los expone
para el panel web. Ejecutar desde la raíz del proyecto:

    uvicorn app.servidor:app --port 8123
"""

import hmac
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agente_foundry import responder as responder_foundry
from app.recomendaciones import generar as generar_recomendaciones
from app.seguridad_http import configurar_seguridad_http
from modulos.base_datos import (
    ErrorBaseDatos,
    contar_lotes_respaldo,
)
from modulos.base_datos import (
    consultar as consultar_bd,
)
from modulos.base_datos import (
    ejecutar as ejecutar_bd,
)
from modulos.base_datos import (
    ejecutar_transaccion as ejecutar_transaccion_bd,
)
from modulos.seguridad import (
    es_direccion_local,
    es_solicitud_local,
    hash_script_inline,
    limpiar_texto,
    mismo_origen,
)

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

ESTATICOS = Path(__file__).parent / "static"
docs_habilitados = os.getenv("NINFAS_ENABLE_DOCS") == "1"
app = FastAPI(
    title="Monitor de Ninfas",
    docs_url="/docs" if docs_habilitados else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs_habilitados else None,
)
configurar_seguridad_http(
    app,
    perfil="panel",
    hash_script=hash_script_inline(ESTATICOS / "index.html"),
)
logger = logging.getLogger(__name__)

def _iso(fecha):
    """Azure SQL guarda GETDATE() en UTC; se marca la zona para que el
    navegador la convierta a la hora local del usuario."""
    return fecha.replace(tzinfo=timezone.utc).isoformat()


def _consultar(query, params=()):
    """Consulta mediante el repositorio sincronizado de Azure SQL."""
    try:
        return consultar_bd(query, params)
    except ErrorBaseDatos as error:
        logger.error("Azure SQL no disponible durante una consulta: %s", error)
        raise HTTPException(
            status_code=503, detail="La base de datos no está disponible temporalmente."
        ) from error


def _ejecutar(query, params=()):
    """Ejecuta mediante el repositorio sincronizado de Azure SQL."""
    try:
        ejecutar_bd(query, params)
    except ErrorBaseDatos as error:
        logger.error("Azure SQL no disponible durante una escritura: %s", error)
        raise HTTPException(
            status_code=503, detail="La base de datos no está disponible temporalmente."
        ) from error


def _ejecutar_transaccion(sentencias):
    """Ejecuta varias mutaciones como una unidad atómica."""
    try:
        ejecutar_transaccion_bd(sentencias)
    except ErrorBaseDatos as error:
        logger.error("Azure SQL no disponible durante una transacción: %s", error)
        raise HTTPException(
            status_code=503, detail="La base de datos no está disponible temporalmente."
        ) from error


def _es_cliente_local(request: Request) -> bool:
    host_cliente = request.client.host if request.client else None
    return es_direccion_local(host_cliente) and es_solicitud_local(
        host_cliente, request.headers
    )


def _verificar_clave_agente(
    request: Request,
    x_ninfas_agent_key: str | None = Header(default=None, include_in_schema=False),
):
    """Protege las herramientas que se expondran a Microsoft Foundry."""
    if not _es_cliente_local(request) and request.url.scheme != "https":
        raise HTTPException(status_code=403, detail="La API remota del agente requiere HTTPS.")
    clave_configurada = os.getenv("NINFAS_AGENT_API_KEY")
    if not clave_configurada:
        raise HTTPException(
            status_code=503,
            detail="La clave del agente no esta configurada en el servidor.",
        )
    if len(clave_configurada) < 32:
        raise HTTPException(
            status_code=503,
            detail="La clave del agente debe contener al menos 32 caracteres.",
        )
    if not x_ninfas_agent_key or not hmac.compare_digest(
        x_ninfas_agent_key, clave_configurada
    ):
        raise HTTPException(status_code=401, detail="Clave de agente invalida.")


def _verificar_origen_panel(request: Request) -> None:
    sitio = request.headers.get("sec-fetch-site", "").lower()
    if sitio == "cross-site":
        raise HTTPException(status_code=403, detail="Origen de solicitud no permitido.")

    origen = request.headers.get("origin")
    host = request.headers.get("host", "")
    if origen and not mismo_origen(origen, request.url.scheme, host):
        raise HTTPException(status_code=403, detail="Origen de solicitud no permitido.")


def _proteger_operacion_panel(
    request: Request,
    x_ninfas_admin_key: str | None = Header(default=None, include_in_schema=False),
) -> None:
    """Protege escrituras y llamadas que generan costo en Foundry."""
    _verificar_origen_panel(request)
    clave = os.getenv("NINFAS_ADMIN_API_KEY")
    local = _es_cliente_local(request)
    if clave:
        if len(clave) < 32:
            raise HTTPException(
                status_code=503,
                detail="La clave de administración debe contener al menos 32 caracteres.",
            )
        if not local and request.url.scheme != "https":
            raise HTTPException(
                status_code=403,
                detail="La administración remota requiere HTTPS.",
            )
        if not x_ninfas_admin_key or not hmac.compare_digest(x_ninfas_admin_key, clave):
            raise HTTPException(
                status_code=401,
                detail="Se requiere la clave de administración.",
                headers={"WWW-Authenticate": "NinfasAdminKey"},
            )
        return

    if not local:
        raise HTTPException(
            status_code=403,
            detail=(
                "Las operaciones de escritura están limitadas al equipo local. "
                "Configura NINFAS_ADMIN_API_KEY para habilitarlas remotamente."
            ),
        )


app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


@app.get("/")
def portada():
    return FileResponse(ESTATICOS / "index.html")


# =====================================================================
#  HERRAMIENTAS DEL AGENTE (SOLO LECTURA)
# =====================================================================


@app.get(
    "/agent/estado-ave",
    operation_id="obtener_estado_ave",
    summary="Obtiene el resumen reciente de una ninfa registrada",
    dependencies=[Depends(_verificar_clave_agente)],
)
def obtener_estado_ave(
    nombre: str = Query(min_length=1, max_length=50),
    horas: int = Query(default=24, ge=1, le=168),
):
    """Herramienta para Foundry: consulta segura y acotada por nombre de ave."""
    nombre = limpiar_texto(nombre, 50)
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre del ave no es válido.")
    aves = _consultar(
        """
        SELECT Id, Nombre, Color, Notas
        FROM Aves
        WHERE LOWER(Nombre) = LOWER(?)
        """,
        (nombre,),
    )
    if not aves:
        raise HTTPException(status_code=404, detail=f"No existe un ave llamada '{nombre}'.")

    ave = aves[0]
    consumo = _consultar(
        """
        SELECT
            SUM(CASE WHEN Accion = 'Alimentacion' THEN 1 ELSE 0 END) AS Comidas,
            SUM(CASE WHEN Accion = 'Hidratacion' THEN 1 ELSE 0 END) AS Bebidas,
            SUM(CASE WHEN Accion = 'Alimentacion' THEN ISNULL(Valor_Numerico, 0) ELSE 0 END) AS SegComiendo,
            SUM(CASE WHEN Accion = 'Hidratacion' THEN ISNULL(Valor_Numerico, 0) ELSE 0 END) AS SegBebiendo,
            MAX(CASE WHEN Accion = 'Alimentacion' THEN Fecha END) AS UltimaComida,
            MAX(CASE WHEN Accion = 'Hidratacion' THEN Fecha END) AS UltimaBebida
        FROM BitacoraAves
        WHERE AveId = ?
          AND Categoria IN ('Accion', 'Comportamiento')
          AND Estado_Observado IN ('Fin', 'Activo')
          AND Fecha >= DATEADD(hour, -?, GETDATE())
        """,
        (ave["Id"], horas),
    )[0]

    return {
        "ave": {
            "id": ave["Id"],
            "nombre": ave["Nombre"],
            "color": ave["Color"],
        },
        "periodo_horas": horas,
        "alimentacion": {
            "eventos": int(consumo["Comidas"] or 0),
            "duracion_segundos": float(consumo["SegComiendo"] or 0),
            "ultima_vez": _iso(consumo["UltimaComida"]) if consumo["UltimaComida"] else None,
        },
        "hidratacion": {
            "eventos": int(consumo["Bebidas"] or 0),
            "duracion_segundos": float(consumo["SegBebiendo"] or 0),
            "ultima_vez": _iso(consumo["UltimaBebida"]) if consumo["UltimaBebida"] else None,
        },
        "estado_global_reciente": estado_actual(),
        "limitacion": (
            "El animo, actividad y audio actuales son mediciones globales de la jaula; "
            "todavia no se calculan de forma individual por ave."
        ),
    }


@app.get(
    "/agent/recomendaciones",
    operation_id="obtener_recomendaciones_monitor",
    summary="Obtiene las recomendaciones actuales del monitor",
    dependencies=[Depends(_verificar_clave_agente)],
)
def obtener_recomendaciones_monitor():
    """Herramienta para Foundry: entrega recomendaciones del sistema global."""
    return {
        "alcance": "global_para_la_jaula",
        "recomendaciones": recomendaciones(),
        "limitacion": "Las recomendaciones actuales no se asignan individualmente a una ninfa.",
    }


def _ejecutar_herramienta_asistente(nombre: str, argumentos: dict) -> dict:
    """Adaptador local y cerrado para las funciones que puede llamar Foundry."""
    if nombre == "obtener_estado_ave":
        horas = argumentos.get("horas", 24)
        nombre_ave = str(argumentos.get("nombre", "")).strip()
        if isinstance(horas, bool) or not isinstance(horas, int) or not 1 <= horas <= 168:
            return {"error": "El periodo debe estar entre 1 y 168 horas."}
        nombre_ave = limpiar_texto(nombre_ave, 50)
        if not nombre_ave:
            return {"error": "Debes indicar el nombre de la ninfa."}
        try:
            return obtener_estado_ave(nombre_ave, horas)
        except HTTPException as error:
            return {"error": error.detail}

    if nombre == "obtener_recomendaciones_monitor":
        return obtener_recomendaciones_monitor()

    return {"error": "Herramienta no permitida."}


@app.get("/agent/openapi.json", include_in_schema=False)
def especificacion_herramientas_agente():
    """OpenAPI reducido para importar solo las herramientas seguras en Foundry."""
    esquema = get_openapi(
        title="Herramientas del Monitor de Ninfas",
        version="1.0.0",
        description="Herramientas de solo lectura para el agente Asistente de Ninfas.",
        routes=app.routes,
    )
    esquema["paths"] = {
        ruta: operaciones
        for ruta, operaciones in esquema["paths"].items()
        if ruta.startswith("/agent/") and ruta != "/agent/openapi.json"
    }
    componentes = esquema.setdefault("components", {})
    componentes.setdefault("securitySchemes", {})["NinfasAgentKey"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Ninfas-Agent-Key",
        "description": "Clave privada configurada como secreto en el servidor y Foundry.",
    }
    for operaciones in esquema["paths"].values():
        for operacion in operaciones.values():
            operacion["security"] = [{"NinfasAgentKey": []}]
    return esquema


@app.get("/api/health")
def healthcheck():
    """Diagnóstico operativo de base de datos, frescura del monitor y cola local."""
    lotes_respaldo = contar_lotes_respaldo()
    try:
        filas = consultar_bd(
            """
            SELECT MAX(Fecha) AS UltimaFecha
            FROM BitacoraAves
            WHERE Categoria = 'Snapshot'
              AND Fecha >= DATEADD(day, -7, GETDATE())
            """
        )
        bd_disponible = True
        ultima = filas[0]["UltimaFecha"] if filas else None
    except ErrorBaseDatos:
        bd_disponible = False
        ultima = None

    ahora = datetime.now(timezone.utc)
    ultimo_iso = None
    minutos_sin_reporte = None
    monitor_activo = False

    if ultima is not None:
        ultima_utc = ultima.replace(tzinfo=timezone.utc)
        ultimo_iso = ultima_utc.isoformat()
        minutos_sin_reporte = round(
            max(0.0, (ahora - ultima_utc).total_seconds() / 60.0), 1
        )
        monitor_activo = minutos_sin_reporte <= 30.0

    estado_general = (
        "ok"
        if (bd_disponible and monitor_activo and lotes_respaldo == 0)
        else "degraded"
    )
    return {
        "status": estado_general,
        "base_datos_disponible": bd_disponible,
        "monitor_activo": monitor_activo,
        "ultimo_snapshot_utc": ultimo_iso,
        "minutos_sin_reporte": minutos_sin_reporte,
        "lotes_pendientes_respaldo": lotes_respaldo,
    }


@app.get("/api/estado")
def estado_actual():
    """Último valor de cada métrica del snapshot (ánimo, actividad, etc.)."""
    filas = _consultar(
        """
        SELECT Accion, Valor_Numerico, Estado_Observado, Fecha, Notas
        FROM (
            SELECT Accion, Valor_Numerico, Estado_Observado, Fecha, Notas,
                   ROW_NUMBER() OVER (PARTITION BY Accion ORDER BY Fecha DESC) AS rn
            FROM BitacoraAves
            WHERE Categoria = 'Snapshot'
              AND Fecha >= DATEADD(day, -7, GETDATE())
        ) t
        WHERE rn = 1
        """
    )
    return {
        f["Accion"]: {
            "valor": float(f["Valor_Numerico"] or 0),
            "estado": f["Estado_Observado"],
            "fecha": _iso(f["Fecha"]),
        }
        for f in filas
    }


@app.get("/api/historial")
def historial(horas: int = Query(default=24, ge=1, le=168)):
    """Snapshots dentro de la ventana pedida, para los gráficos."""
    filas = _consultar(
        """
        SELECT Fecha, Accion, Valor_Numerico, Estado_Observado
        FROM BitacoraAves
        WHERE Categoria = 'Snapshot' AND Fecha >= DATEADD(hour, -?, GETDATE())
        ORDER BY Fecha ASC
        """,
        (horas,),
    )
    return [
        {
            "fecha": _iso(f["Fecha"]),
            "metrica": f["Accion"],
            "valor": float(f["Valor_Numerico"] or 0),
            "estado": f["Estado_Observado"],
        }
        for f in filas
    ]


@app.get("/api/acciones")
def acciones(horas: int = Query(default=48, ge=1, le=168)):
    """Eventos de comer y beber (incluye los registros antiguos)."""
    filas = _consultar(
        """
        SELECT TOP (500)
               b.Fecha, b.Accion, b.Valor_Numerico, b.Estado_Observado, b.Notas,
               b.TrackId, a.Nombre AS Ave
        FROM BitacoraAves b
        LEFT JOIN Aves a ON a.Id = b.AveId
        WHERE b.Categoria IN ('Accion', 'Comportamiento')
          AND b.Accion IN ('Alimentacion', 'Hidratacion')
          AND b.Estado_Observado IN ('Fin', 'Activo')
          AND b.Fecha >= DATEADD(hour, -?, GETDATE())
        ORDER BY b.Fecha DESC
        """,
        (horas,),
    )
    return [
        {
            "fecha": _iso(f["Fecha"]),
            "accion": f["Accion"],
            "duracion": float(f["Valor_Numerico"] or 0),
            "estado": f["Estado_Observado"],
            "notas": f["Notas"],
            "track": f["TrackId"],
            "ave": f["Ave"],
        }
        for f in filas
    ]


@app.get("/api/recomendaciones")
def recomendaciones():
    """Analiza las últimas 24 h y genera recomendaciones con el motor de reglas."""
    def utc(fecha):
        return fecha.replace(tzinfo=timezone.utc)

    snapshots = [
        {
            "fecha": utc(f["Fecha"]),
            "metrica": f["Accion"],
            "valor": float(f["Valor_Numerico"] or 0),
            "estado": f["Estado_Observado"],
        }
        for f in _consultar(
            """
            SELECT Fecha, Accion, Valor_Numerico, Estado_Observado
            FROM BitacoraAves
            WHERE Categoria = 'Snapshot' AND Fecha >= DATEADD(hour, -24, GETDATE())
            ORDER BY Fecha ASC
            """
        )
    ]

    # Deriva el último estado por métrica desde los snapshots de 24 h en memoria,
    # evitando una cuarta consulta SQL con ROW_NUMBER() cuando hay datos recientes.
    estado = {}
    for snap in snapshots:
        estado[snap["metrica"]] = {
            "valor": snap["valor"],
            "estado": snap["estado"],
            "fecha": snap["fecha"],
        }
    if not estado:
        estado_filas = _consultar(
            """
            SELECT Accion, Valor_Numerico, Estado_Observado, Fecha
            FROM (
                SELECT Accion, Valor_Numerico, Estado_Observado, Fecha,
                       ROW_NUMBER() OVER (PARTITION BY Accion ORDER BY Fecha DESC) AS rn
                FROM BitacoraAves
                WHERE Categoria = 'Snapshot'
                  AND Fecha >= DATEADD(day, -7, GETDATE())
            ) t WHERE rn = 1
            """
        )
        estado = {
            f["Accion"]: {
                "valor": float(f["Valor_Numerico"] or 0),
                "estado": f["Estado_Observado"],
                "fecha": utc(f["Fecha"]),
            }
            for f in estado_filas
        }

    acciones_24h = [
        {"fecha": utc(f["Fecha"]), "accion": f["Accion"], "estado": f["Estado_Observado"]}
        for f in _consultar(
            """
            SELECT Fecha, Accion, Estado_Observado
            FROM BitacoraAves
            WHERE Categoria IN ('Accion', 'Comportamiento')
              AND Fecha >= DATEADD(hour, -24, GETDATE())
            """
        )
    ]

    aves = [{"nombre": f["Nombre"]} for f in _consultar("SELECT Nombre FROM Aves ORDER BY Id")]

    return generar_recomendaciones(estado, snapshots, acciones_24h, aves)


class ModeloEstricto(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class ConsultaAsistente(ModeloEstricto):
    pregunta: str = Field(min_length=1, max_length=600)


@app.post("/api/asistente", dependencies=[Depends(_proteger_operacion_panel)])
def consultar_asistente(consulta: ConsultaAsistente):
    """Devuelve una respuesta de Foundry sin exponer credenciales al navegador."""
    pregunta = limpiar_texto(consulta.pregunta, 600, multilinea=True)
    if not pregunta:
        raise HTTPException(status_code=400, detail="Escribe una pregunta para el asistente.")

    try:
        respuesta = responder_foundry(pregunta, _ejecutar_herramienta_asistente)
    except RuntimeError as error:
        logger.warning("Asistente Foundry sin configurar: %s", error)
        raise HTTPException(
            status_code=503,
            detail="El asistente no esta configurado. Revisa las variables FOUNDRY_* en .env.",
        ) from error
    except Exception as error:
        logger.exception("Error al consultar Microsoft Foundry")
        raise HTTPException(
            status_code=502,
            detail="No fue posible obtener una respuesta del asistente. Intenta nuevamente.",
        ) from error

    return {"respuesta": respuesta, "fuente": "Microsoft Foundry"}


@app.get("/api/aves_stats")
def aves_stats(horas: int = Query(default=24, ge=1, le=168)):
    """Estadísticas de comer/beber por ave en la ventana pedida."""
    filas = _consultar(
        """
        SELECT a.Id, a.Nombre, a.Color,
               b.Accion, b.Valor_Numerico, b.Fecha
        FROM Aves a
        LEFT JOIN BitacoraAves b
          ON b.AveId = a.Id
         AND b.Categoria IN ('Accion', 'Comportamiento')
         AND b.Accion IN ('Alimentacion', 'Hidratacion')
         AND b.Estado_Observado IN ('Fin', 'Activo')
         AND b.Fecha >= DATEADD(hour, -?, GETDATE())
        ORDER BY a.Id, b.Fecha
        """,
        (horas,),
    )

    aves = {}
    for f in filas:
        ave = aves.setdefault(f["Id"], {
            "id": f["Id"],
            "nombre": f["Nombre"],
            "color": f["Color"],
            "comidas": 0, "seg_comiendo": 0.0, "ultima_comida": None,
            "bebidas": 0, "seg_bebiendo": 0.0, "ultima_bebida": None,
        })
        if f["Accion"] == "Alimentacion":
            ave["comidas"] += 1
            ave["seg_comiendo"] += float(f["Valor_Numerico"] or 0)
            ave["ultima_comida"] = _iso(f["Fecha"])
        elif f["Accion"] == "Hidratacion":
            ave["bebidas"] += 1
            ave["seg_bebiendo"] += float(f["Valor_Numerico"] or 0)
            ave["ultima_bebida"] = _iso(f["Fecha"])

    sin_asignar = _consultar(
        """
        SELECT COUNT(*) AS n FROM BitacoraAves b
        WHERE b.Categoria IN ('Accion', 'Comportamiento')
          AND b.Accion IN ('Alimentacion', 'Hidratacion')
          AND b.Estado_Observado IN ('Fin', 'Activo')
          AND b.AveId IS NULL
          AND b.Fecha >= DATEADD(hour, -?, GETDATE())
        """,
        (horas,),
    )[0]["n"]

    return {"aves": list(aves.values()), "sin_identificar": sin_asignar}


# =====================================================================
#  AVES (nombres de cada ninfa)
# =====================================================================


class AveNueva(ModeloEstricto):
    nombre: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, max_length=100)
    notas: str | None = Field(default=None, max_length=500)


@app.get("/api/aves")
def listar_aves():
    filas = _consultar(
        "SELECT Id, Nombre, Color, Notas, FechaRegistro FROM Aves ORDER BY Id"
    )
    return [
        {
            "id": f["Id"],
            "nombre": f["Nombre"],
            "color": f["Color"],
            "notas": f["Notas"],
            "registrada": _iso(f["FechaRegistro"]),
        }
        for f in filas
    ]


@app.post("/api/aves", dependencies=[Depends(_proteger_operacion_panel)])
def crear_ave(ave: AveNueva):
    nombre = limpiar_texto(ave.nombre, 50)
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    color = limpiar_texto(ave.color, 100)
    notas = limpiar_texto(ave.notas, 500, multilinea=True)
    _ejecutar(
        "INSERT INTO Aves (Nombre, Color, Notas) VALUES (?, ?, ?)",
        (nombre, color, notas),
    )
    return {"ok": True}


@app.put("/api/aves/{ave_id}", dependencies=[Depends(_proteger_operacion_panel)])
def editar_ave(ave: AveNueva, ave_id: int = PathParam(gt=0)):
    nombre = limpiar_texto(ave.nombre, 50)
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
    color = limpiar_texto(ave.color, 100)
    notas = limpiar_texto(ave.notas, 500, multilinea=True)
    _ejecutar(
        "UPDATE Aves SET Nombre = ?, Color = ?, Notas = ? WHERE Id = ?",
        (nombre, color, notas, ave_id),
    )
    return {"ok": True}


@app.delete("/api/aves/{ave_id}", dependencies=[Depends(_proteger_operacion_panel)])
def borrar_ave(ave_id: int = PathParam(gt=0)):
    _ejecutar_transaccion(
        [
            ("UPDATE BitacoraAves SET AveId = NULL WHERE AveId = ?", (ave_id,)),
            ("DELETE FROM Aves WHERE Id = ?", (ave_id,)),
        ]
    )
    return {"ok": True}


@app.get("/api/cambios_animo")
def cambios_animo(horas: int = Query(default=48, ge=1, le=168)):
    """Historial de cambios de estado de ánimo."""
    filas = _consultar(
        """
        SELECT Fecha, Estado_Observado, Notas
        FROM BitacoraAves
        WHERE Categoria = 'Estado' AND Fecha >= DATEADD(hour, -?, GETDATE())
        ORDER BY Fecha ASC
        """,
        (horas,),
    )
    return [
        {"fecha": _iso(f["Fecha"]), "animo": f["Estado_Observado"], "contexto": f["Notas"]}
        for f in filas
    ]
