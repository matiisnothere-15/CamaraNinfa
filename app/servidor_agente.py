"""API publica y reducida para Microsoft Foundry.

Ejecutar de forma independiente del panel:

    uvicorn app.servidor_agente:app --port 8124

Solo publica herramientas de lectura. La API del panel sigue en el puerto 8123.
"""

import os

from fastapi import Depends, FastAPI
from fastapi.openapi.utils import get_openapi

from app.seguridad_http import configurar_seguridad_http
from app.servidor import (
    _verificar_clave_agente,
    obtener_estado_ave,
    obtener_recomendaciones_monitor,
)

app = FastAPI(
    title="Herramientas del Monitor de Ninfas",
    version="1.0.0",
    description="API de solo lectura para el agente Asistente de Ninfas.",
    docs_url=None,
    redoc_url=None,
)
configurar_seguridad_http(app, perfil="agente")

app.get(
    "/estado-ave",
    operation_id="obtener_estado_ave",
    summary="Obtiene el resumen reciente de una ninfa registrada",
    dependencies=[Depends(_verificar_clave_agente)],
)(obtener_estado_ave)

app.get(
    "/recomendaciones",
    operation_id="obtener_recomendaciones_monitor",
    summary="Obtiene las recomendaciones actuales del monitor",
    dependencies=[Depends(_verificar_clave_agente)],
)(obtener_recomendaciones_monitor)


def _openapi_agente():
    if app.openapi_schema:
        return app.openapi_schema

    esquema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    componentes = esquema.setdefault("components", {})
    componentes.setdefault("securitySchemes", {})["NinfasAgentKey"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Ninfas-Agent-Key",
        "description": "Clave privada del agente.",
    }
    for operaciones in esquema["paths"].values():
        for operacion in operaciones.values():
            operacion["security"] = [{"NinfasAgentKey": []}]

    # Foundry necesita una URL absoluta para ejecutar las operaciones del spec.
    # En desarrollo se configura con la URL temporal de Microsoft Dev Tunnels.
    url_publica = os.getenv("NINFAS_AGENT_PUBLIC_URL")
    if url_publica:
        esquema["servers"] = [{"url": url_publica.rstrip("/")}]
    app.openapi_schema = esquema
    return app.openapi_schema


app.openapi = _openapi_agente
