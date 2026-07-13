"""Resolución común de webcam, URL de video y cámaras Tapo."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ESQUEMAS_VIDEO = {"http", "https", "rtsp", "rtsps"}


def cargar_entorno(ruta: Path | None = None) -> bool:
    """Carga `.env` cuando python-dotenv está disponible."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    archivo = ruta or Path(__file__).resolve().parent.parent / ".env"
    return bool(load_dotenv(archivo))


def parsear_fuente(valor: str | int) -> str | int:
    """Convierte un índice o valida una URL compatible con OpenCV."""
    if isinstance(valor, int):
        if valor < 0:
            raise ValueError("El índice de cámara no puede ser negativo.")
        return valor

    texto = str(valor).strip()
    if texto.isdecimal():
        return int(texto)

    url = urlsplit(texto)
    if url.scheme.lower() not in ESQUEMAS_VIDEO or not url.netloc:
        raise ValueError(
            "La fuente debe ser un índice de webcam o una URL http(s)/rtsp(s)."
        )
    return texto


def construir_url_tapo(
    usuario: str | None = None,
    contrasena: str | None = None,
    host: str | None = None,
) -> str | None:
    """Construye la URL Tapo sin dejar caracteres de credenciales sin escapar."""
    valores = (
        usuario if usuario is not None else os.getenv("TAPO_USER"),
        contrasena if contrasena is not None else os.getenv("TAPO_PASS"),
        host if host is not None else os.getenv("TAPO_IP"),
    )
    presentes = [bool(valor and valor.strip()) for valor in valores]
    if not any(presentes):
        return None
    if not all(presentes):
        raise ValueError("TAPO_USER, TAPO_PASS y TAPO_IP deben configurarse juntos.")

    usuario_real, contrasena_real, host_real = (valor.strip() for valor in valores)
    if any(caracter in host_real for caracter in "/@?#"):
        raise ValueError("TAPO_IP debe contener solo una IP o nombre de host.")
    return (
        f"rtsp://{quote(usuario_real, safe='')}:{quote(contrasena_real, safe='')}"
        f"@{host_real}:554/stream2"
    )


def resolver_fuente(explicita: str | int | None = None) -> str | int:
    """Resuelve fuente explícita, URL genérica, Tapo o webcam, en ese orden."""
    if explicita is not None and str(explicita).strip():
        return parsear_fuente(explicita)

    url_generica = os.getenv("CAMARA_RTSP_URL", "").strip()
    if url_generica:
        return parsear_fuente(url_generica)

    url_tapo = construir_url_tapo()
    if url_tapo:
        return url_tapo

    indice = os.getenv("CAMARA_PC_INDICE", "0")
    return parsear_fuente(indice)


def es_rtsp(fuente: str | int) -> bool:
    return isinstance(fuente, str) and urlsplit(fuente).scheme.lower() in {"rtsp", "rtsps"}


def describir_fuente(fuente: str | int) -> str:
    """Describe una fuente ocultando cualquier usuario o contraseña."""
    if isinstance(fuente, int):
        return f"webcam local {fuente}"

    url = urlsplit(fuente)
    host = url.hostname or "host desconocido"
    if url.port:
        host = f"{host}:{url.port}"
    segura = urlunsplit((url.scheme, host, url.path, "", ""))
    return segura
