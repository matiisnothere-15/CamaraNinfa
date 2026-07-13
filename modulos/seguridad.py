"""Utilidades de seguridad independientes del framework web."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import threading
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit


class LimitadorSolicitudes:
    """Limitador en memoria por ventana móvil, seguro entre hilos."""

    def __init__(self):
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._registros = 0

    def registrar(
        self,
        clave: str,
        limite: int,
        ventana_segundos: float,
        ahora: float | None = None,
    ) -> int | None:
        """Retorna segundos de espera si se excedió el límite; si no, ``None``."""
        ahora = time.monotonic() if ahora is None else ahora
        inicio = ahora - ventana_segundos
        with self._lock:
            self._registros += 1
            if self._registros % 1_000 == 0:
                caducadas = [
                    otra_clave
                    for otra_clave, otros_eventos in self._eventos.items()
                    if not otros_eventos or otros_eventos[-1] <= inicio
                ]
                for otra_clave in caducadas:
                    self._eventos.pop(otra_clave, None)
            eventos = self._eventos[clave]
            while eventos and eventos[0] <= inicio:
                eventos.popleft()
            if len(eventos) >= limite:
                return max(1, int(ventana_segundos - (ahora - eventos[0]) + 0.999))
            eventos.append(ahora)
        return None


def es_direccion_local(host: str | None) -> bool:
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def mismo_origen(origen: str, esquema: str, host: str) -> bool:
    """Compara origen y destino normalizando sus puertos predeterminados."""

    def normalizar(url: str):
        partes = urlsplit(url)
        puerto = partes.port
        if puerto is None:
            puerto = 443 if partes.scheme == "https" else 80
        return partes.scheme.lower(), (partes.hostname or "").lower(), puerto

    try:
        return normalizar(origen) == normalizar(f"{esquema}://{host}")
    except ValueError:
        return False


def limpiar_texto(valor: str | None, maximo: int, multilinea: bool = False) -> str | None:
    """Normaliza Unicode y elimina caracteres de control antes de persistir."""
    if valor is None:
        return None
    valor = unicodedata.normalize("NFC", valor)
    permitido = {"\n", "\t"} if multilinea else set()
    valor = "".join(
        caracter
        for caracter in valor
        if caracter in permitido or not unicodedata.category(caracter).startswith("C")
    ).strip()
    if len(valor) > maximo:
        raise ValueError(f"El texto supera el máximo de {maximo} caracteres.")
    return valor or None


def hash_script_inline(ruta_html: str | Path) -> str:
    """Calcula el hash CSP del único bloque JavaScript inline del panel."""
    html = Path(ruta_html).read_text(encoding="utf-8")
    bloques = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL | re.IGNORECASE)
    if len(bloques) != 1:
        raise ValueError("El panel debe contener exactamente un script inline.")
    digest = hashlib.sha256(bloques[0].encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")
