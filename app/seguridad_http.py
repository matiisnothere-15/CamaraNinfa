"""Cabeceras, tamaño máximo y rate limiting compartidos por las APIs."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from modulos.seguridad import LimitadorSolicitudes

_limitador = LimitadorSolicitudes()


class _CuerpoDemasiadoGrande(Exception):
    pass


class LimiteCuerpoMiddleware:
    """Cuenta bytes reales del stream, incluso si no llega Content-Length."""

    def __init__(self, app, maximo: int = 16_384):
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        recibidos = 0

        async def receive_limitado():
            nonlocal recibidos
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                recibidos += len(mensaje.get("body", b""))
                if recibidos > self.maximo:
                    raise _CuerpoDemasiadoGrande
            return mensaje

        try:
            await self.app(scope, receive_limitado, send)
        except _CuerpoDemasiadoGrande:
            respuesta = JSONResponse(
                {"detail": "El cuerpo de la solicitud es demasiado grande."},
                status_code=413,
            )
            await respuesta(scope, receive, send)


def _hosts_permitidos() -> list[str]:
    valor = os.getenv("NINFAS_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver,[::1]")
    hosts = [host.strip() for host in valor.split(",") if host.strip()]
    publica = os.getenv("NINFAS_AGENT_PUBLIC_URL", "")
    try:
        hostname_publico = urlsplit(publica).hostname
    except ValueError:
        hostname_publico = None
    if hostname_publico and hostname_publico not in hosts:
        hosts.append(hostname_publico)
    return hosts


def _agregar_cabeceras(respuesta, csp: str) -> None:
    respuesta.headers["Content-Security-Policy"] = csp
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    respuesta.headers["X-Frame-Options"] = "DENY"


def configurar_seguridad_http(app, perfil: str, hash_script: str | None = None) -> None:
    """Instala defensas HTTP antes de registrar las rutas de una aplicación."""
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts_permitidos())
    app.add_middleware(LimiteCuerpoMiddleware, maximo=16_384)

    script_src = f"'self' 'sha256-{hash_script}'" if hash_script else "'none'"
    csp = (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )

    @app.middleware("http")
    async def seguridad_http(request, call_next):
        contenido = request.headers.get("content-length")
        if contenido:
            try:
                demasiado_grande = int(contenido) > 16_384
            except ValueError:
                demasiado_grande = True
            if demasiado_grande:
                respuesta = JSONResponse(
                    {"detail": "El cuerpo de la solicitud es demasiado grande."},
                    status_code=413,
                )
                _agregar_cabeceras(respuesta, csp)
                return respuesta

        host_cliente = request.client.host if request.client else "desconocido"
        ruta = request.url.path
        if perfil == "agente" or ruta.startswith("/agent/"):
            grupo, limite = "agente", 60
        elif ruta == "/api/asistente":
            grupo, limite = "asistente", 8
        elif ruta.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            grupo, limite = "escritura", 30
        elif ruta.startswith("/api/"):
            grupo, limite = "lectura", 240
        else:
            grupo, limite = "web", 300

        espera = _limitador.registrar(f"{perfil}:{grupo}:{host_cliente}", limite, 60)
        if espera is not None:
            respuesta = JSONResponse(
                {"detail": "Demasiadas solicitudes. Intenta nuevamente más tarde."},
                status_code=429,
                headers={"Retry-After": str(espera)},
            )
            _agregar_cabeceras(respuesta, csp)
            return respuesta

        respuesta = await call_next(request)
        _agregar_cabeceras(respuesta, csp)
        if ruta.startswith(("/api/", "/agent/")) or perfil == "agente":
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta
