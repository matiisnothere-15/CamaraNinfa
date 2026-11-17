"""Notificaciones push para alertas clínicas y estados críticos del monitor.

Admite envío a Telegram Bot API (``TELEGRAM_BOT_TOKEN`` + ``TELEGRAM_CHAT_ID``)
y/o a un Webhook HTTP(S) compatible con Discord, Slack o receptores genéricos
(``NINFAS_ALERT_WEBHOOK_URL``), usando una cola asíncrona con enfriamiento
(cooldown) por clave para no bloquear el bucle de video ni saturar al usuario.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from modulos.seguridad import es_direccion_local, limpiar_texto


def _validar_url_webhook(url: str) -> str | None:
    """Permite HTTPS para destinos remotos o HTTP únicamente en loopback."""
    if not url or not url.strip():
        return None
    limpia = url.strip()
    partes = urlsplit(limpia)
    if not partes.hostname or partes.username or partes.password:
        return None
    if partes.scheme == "https":
        return limpia
    if partes.scheme == "http" and es_direccion_local(partes.hostname):
        return limpia
    return None


class NotificadorAlertas:
    """Despacha alertas clínicas con control de enfriamiento (cooldown) por clave."""

    _SENTINELA = object()

    def __init__(
        self,
        webhook_url: str | None = None,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
        cooldown_segundos: float = 1800.0,
        enviador_http: Callable[[str, dict], bool] | None = None,
    ) -> None:
        raw_webhook = (
            os.getenv("NINFAS_ALERT_WEBHOOK_URL", "")
            if webhook_url is None
            else webhook_url
        )
        self.webhook_url = _validar_url_webhook(raw_webhook)
        if raw_webhook and raw_webhook.strip() and self.webhook_url is None:
            print(
                "NINFAS_ALERT_WEBHOOK_URL ignorada: se requiere HTTPS para destinos remotos."
            )

        self.telegram_token = (
            os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if telegram_token is None
            else telegram_token.strip()
        )
        self.telegram_chat_id = (
            os.getenv("TELEGRAM_CHAT_ID", "").strip()
            if telegram_chat_id is None
            else telegram_chat_id.strip()
        )
        self.cooldown_segundos = max(0.0, float(cooldown_segundos))
        self._enviador_http = enviador_http or self._post_json
        self._ultimo_envio: dict[str, float] = {}
        self._cola: queue.Queue = queue.Queue()
        self._hilo: threading.Thread | None = None
        self._cerrado = False

    @property
    def telegram_activo(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def activo(self) -> bool:
        return bool(self.webhook_url or self.telegram_activo)

    @staticmethod
    def _post_json(url: str, payload: dict) -> bool:
        datos = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            url,
            data=datos,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "MonitorDeNinfas/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=5) as resp:
                return 200 <= resp.status < 300
        except (HTTPError, URLError, TimeoutError, OSError):
            print("No fue posible entregar la notificación externa.")
            return False

    def _debe_enviar(self, clave: str, ahora: float) -> bool:
        previo = self._ultimo_envio.get(clave)
        if previo is not None and (ahora - previo) < self.cooldown_segundos:
            return False
        self._ultimo_envio[clave] = ahora
        return True

    def enviar_sincrono(
        self,
        clave: str,
        mensaje: str,
        nivel: str = "critica",
        ahora: float | None = None,
    ) -> bool:
        """Envía de forma inmediata si el canal está activo y no está en cooldown."""
        if not self.activo:
            return False
        texto = limpiar_texto(mensaje, 500, multilinea=True)
        if not texto:
            return False

        instante = time.monotonic() if ahora is None else ahora
        if not self._debe_enviar(clave, instante):
            return False

        prefijo = (
            "[VIGILANCIA CLINICA]"
            if nivel == "vigilancia"
            else "[ALERTA CRITICA]"
        )
        cuerpo_final = f"{prefijo} Monitor de Ninfas: {texto}"
        exito = False

        if self.webhook_url:
            payload_webhook = {
                "content": cuerpo_final,
                "text": cuerpo_final,
                "clave": clave,
                "nivel": nivel,
            }
            exito = self._enviador_http(self.webhook_url, payload_webhook) or exito

        if self.telegram_activo:
            url_tg = (
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            )
            payload_tg = {
                "chat_id": self.telegram_chat_id,
                "text": cuerpo_final,
            }
            exito = self._enviador_http(url_tg, payload_tg) or exito

        return exito

    def start(self) -> "NotificadorAlertas":
        if not self.activo or self._cerrado:
            return self
        if self._hilo is None:
            self._hilo = threading.Thread(
                target=self._procesar,
                name="alert-notifier",
                daemon=True,
            )
            self._hilo.start()
        return self

    def notificar_async(
        self, clave: str, mensaje: str, nivel: str = "critica"
    ) -> bool:
        """Encola una alerta para envío en segundo plano sin bloquear el video."""
        if not self.activo or self._cerrado:
            return False
        self.start()
        self._cola.put((clave, mensaje, nivel))
        return True

    def _procesar(self) -> None:
        while True:
            item = self._cola.get()
            try:
                if item is self._SENTINELA:
                    return
                clave, mensaje, nivel = item
                self.enviar_sincrono(clave, mensaje, nivel)
            except Exception as error:
                print(f"Error en cola de notificaciones: {error}")
            finally:
                self._cola.task_done()

    def stop(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        if self._hilo is None:
            return
        self._cola.join()
        self._cola.put(self._SENTINELA)
        self._hilo.join(timeout=5)
        self._hilo = None
