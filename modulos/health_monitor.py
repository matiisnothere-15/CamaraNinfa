import os
import time
from datetime import datetime


class HealthMonitor:
    MAX_BRECHA_MONITOREO = 900.0

    def __init__(
        self,
        aves=None,
        estado_inicial=None,
        sensibilidad_clinica=True,
        ultimo_snapshot_ts=None,
        modo_diurno=True,
        horario_diurno=None,
    ):
        """Monitorea cuanto tiempo lleva cada ave sin comer/beber.

        aves: lista de nombres (ej: ["Yukki", "Mushu"]). Si no se pasa,
        se monitorea un unico registro general.
        sensibilidad_clinica: si es True (predeterminado), una accion sin
        identidad confirmada NO reinicia el contador individual de las aves
        registradas, priorizando detectar si un individuo deja de comer/beber.
        """
        now = time.time()
        self.aves = list(aves) if aves else ["General"]
        self.sensibilidad_clinica = bool(sensibilidad_clinica)

        # ave -> timestamps de ultima comida/bebida. Cuando Azure SQL contiene
        # historial reciente se restaura para no reiniciar el contador; si hubo
        # una brecha mayor a MAX_BRECHA_MONITOREO sin Snapshots se reinicia en
        # observacion tras apagado para evitar falsas alertas en el segundo cero.
        estado_inicial = estado_inicial or {}
        snapshot_raw = (
            ultimo_snapshot_ts
            if ultimo_snapshot_ts is not None
            else estado_inicial.get("__ultimo_snapshot__")
        )
        snapshot_previo = (
            float(snapshot_raw)
            if isinstance(snapshot_raw, (int, float))
            and not isinstance(snapshot_raw, bool)
            and snapshot_raw >= 0
            else None
        )
        self.observacion_tras_apagado = bool(
            snapshot_previo is not None
            and (now - snapshot_previo) > self.MAX_BRECHA_MONITOREO
        )

        self.registro = {}
        for ave in self.aves:
            previo = estado_inicial.get(ave, {})
            if not isinstance(previo, dict):
                previo = {}
            self.registro[ave] = {
                "comer": (
                    now
                    if self.observacion_tras_apagado
                    else self._timestamp_valido(previo.get("comer"), now)
                ),
                "beber": (
                    now
                    if self.observacion_tras_apagado
                    else self._timestamp_valido(previo.get("beber"), now)
                ),
            }

        # Ultimo evento observado sin identidad cromatica confirmada (ej: IR).
        self.ultimo_ambiguo = {"comer": None, "beber": None}

        # Configuracion de umbrales (en segundos). 4 horas = 14400
        self.THRESHOLD_EATING = 14400
        self.THRESHOLD_DRINKING = 14400

        self._camara_conectada = True
        self._luz_diurna = bool(modo_diurno)
        self.horario_diurno = self._parsear_horario(
            horario_diurno
            if horario_diurno is not None
            else os.getenv("NINFAS_HORARIO_DIURNO")
        )
        self._ultimo_tick_ts = now
        self.modo_diurno = self._es_observable(now)

    @staticmethod
    def _parsear_horario(valor: str | None) -> tuple[int, int] | None:
        if not valor or not str(valor).strip():
            return None
        partes = [parte.strip() for parte in str(valor).split("-")]
        if len(partes) != 2:
            return None
        try:
            minutos = []
            for parte in partes:
                hora_str, min_str = parte.split(":")
                hora, minuto = int(hora_str), int(min_str)
                if hora == 24 and minuto == 0:
                    minutos.append(1440)
                elif 0 <= hora <= 23 and 0 <= minuto <= 59:
                    minutos.append(hora * 60 + minuto)
                else:
                    return None
            return (minutos[0], minutos[1])
        except (TypeError, ValueError):
            return None

    def _en_horario_diurno(self, ahora: float) -> bool:
        if self.horario_diurno is None:
            return True
        inicio, fin = self.horario_diurno
        momento = datetime.fromtimestamp(ahora)
        minutos = momento.hour * 60 + momento.minute
        if inicio <= fin:
            return inicio <= minutos < fin
        return minutos >= inicio or minutos < fin

    def _es_observable(self, ahora: float) -> bool:
        return (
            self._camara_conectada
            and self._luz_diurna
            and self._en_horario_diurno(ahora)
        )

    def _avanzar_reloj(self, ahora: float) -> None:
        delta = ahora - self._ultimo_tick_ts
        self._ultimo_tick_ts = ahora
        if delta <= 0 or self.modo_diurno:
            return
        for ts in self.registro.values():
            ts["comer"] = min(ahora, ts["comer"] + delta)
            ts["beber"] = min(ahora, ts["beber"] + delta)
        for clave, valor in self.ultimo_ambiguo.items():
            if valor is not None:
                self.ultimo_ambiguo[clave] = min(ahora, valor + delta)

    def actualizar_condiciones(
        self, camara_conectada: bool = True, luz_diurna: bool = True
    ) -> bool:
        """Actualiza si el tiempo transcurrido cuenta como observacion diurna."""
        now = time.time()
        self._avanzar_reloj(now)
        self._camara_conectada = bool(camara_conectada)
        self._luz_diurna = bool(luz_diurna)
        self.modo_diurno = self._es_observable(now)
        return self.modo_diurno

    @staticmethod
    def _timestamp_valido(valor, ahora):
        """Acepta timestamps históricos, pero nunca fechas futuras o inválidas."""
        if not isinstance(valor, (int, float)) or valor < 0 or valor > ahora:
            return ahora
        return float(valor)

    def sincronizar_aves(self, aves) -> bool:
        """Incorpora aves nuevas o renombradas en caliente conservando contadores."""
        nuevas = list(aves) if aves else []
        if not nuevas or nuevas == self.aves:
            return False
        now = time.time()
        self._avanzar_reloj(now)
        nuevo_registro = {}
        for ave in nuevas:
            if ave in self.registro:
                nuevo_registro[ave] = self.registro[ave]
            else:
                nuevo_registro[ave] = {"comer": now, "beber": now}
        self.aves = nuevas
        self.registro = nuevo_registro
        return True

    def register_action(self, action, ave=None):
        """Actualiza los timestamps segun la accion detectada.

        Con sensibilidad_clinica=True, solo actualiza el contador del ave
        cuando su identidad esta confirmada. Si no se pudo identificar al ave
        (ej: vision nocturna sin color), se registra en `ultimo_ambiguo` para
        contexto clinico sin ocultar una posible inanicion individual.
        """
        if not action:
            return

        now = time.time()
        self._avanzar_reloj(now)
        es_alimentacion = "Alimentacion" in action
        es_hidratacion = "Hidratacion" in action
        if not es_alimentacion and not es_hidratacion:
            return

        if ave in self.registro:
            if es_alimentacion:
                self.registro[ave]["comer"] = now
            elif es_hidratacion:
                self.registro[ave]["beber"] = now
            return

        # Evento sin identidad individual confirmada
        if es_alimentacion:
            self.ultimo_ambiguo["comer"] = now
        elif es_hidratacion:
            self.ultimo_ambiguo["beber"] = now

        if not self.sensibilidad_clinica or self.aves == ["General"]:
            for a in self.registro:
                if es_alimentacion:
                    self.registro[a]["comer"] = now
                elif es_hidratacion:
                    self.registro[a]["beber"] = now

    def _hubo_ambiguo_reciente(self, clave, desde_ts, ahora):
        ts_ambiguo = self.ultimo_ambiguo.get(clave)
        if ts_ambiguo is None:
            return False
        return ts_ambiguo > desde_ts and (ahora - ts_ambiguo) <= (
            self.THRESHOLD_EATING if clave == "comer" else self.THRESHOLD_DRINKING
        )

    def check_health(self):
        """Retorna una lista de alertas si se exceden los tiempos.

        Cada alerta es un dict con:
        - tipo: clave estable (ej: "sin_comer:Yukki"), util para no
          registrar la misma alerta dos veces en la base de datos.
        - ave: nombre del ave afectada.
        - nivel: "critica" (nadie comio/bebio) o "vigilancia" (hubo consumo
          sin identificar en la jaula, pero esta ave no fue confirmada).
        - texto: mensaje para mostrar en pantalla (sin emojis, OpenCV
          no los renderiza).
        - horas: tiempo transcurrido en horas.
        """
        alerts = []
        now = time.time()
        self._avanzar_reloj(now)
        self.modo_diurno = self._es_observable(now)
        if not self.modo_diurno:
            return []

        for ave, ts in self.registro.items():
            horas_comer = (now - ts["comer"]) / 3600
            horas_beber = (now - ts["beber"]) / 3600

            if (now - ts["comer"]) > self.THRESHOLD_EATING:
                ambiguo = self._hubo_ambiguo_reciente("comer", ts["comer"], now)
                nivel = "vigilancia" if ambiguo else "critica"
                sufijo = " (ingesta sin ID reciente)" if ambiguo else ""
                alerts.append({
                    "tipo": f"sin_comer:{ave}",
                    "ave": ave,
                    "nivel": nivel,
                    "texto": f"! {ave.upper()} SIN COMER: {horas_comer:.1f}h{sufijo}",
                    "horas": horas_comer,
                })

            if (now - ts["beber"]) > self.THRESHOLD_DRINKING:
                ambiguo = self._hubo_ambiguo_reciente("beber", ts["beber"], now)
                nivel = "vigilancia" if ambiguo else "critica"
                sufijo = " (agua sin ID reciente)" if ambiguo else ""
                alerts.append({
                    "tipo": f"sin_beber:{ave}",
                    "ave": ave,
                    "nivel": nivel,
                    "texto": f"! {ave.upper()} SIN BEBER: {horas_beber:.1f}h{sufijo}",
                    "horas": horas_beber,
                })

        return alerts

    def get_stats(self):
        """Peor caso entre todas las aves + detalle por ave."""
        now = time.time()
        self._avanzar_reloj(now)
        self.modo_diurno = self._es_observable(now)
        eating = max(now - ts["comer"] for ts in self.registro.values())
        drinking = max(now - ts["beber"] for ts in self.registro.values())
        return {
            "eating_sec": eating,
            "drinking_sec": drinking,
            "ultimo_ambiguo": dict(self.ultimo_ambiguo),
            "por_ave": {
                ave: {
                    "eating_sec": now - ts["comer"],
                    "drinking_sec": now - ts["beber"],
                }
                for ave, ts in self.registro.items()
            },
        }
