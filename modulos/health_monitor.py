import time


class HealthMonitor:
    def __init__(self, aves=None, estado_inicial=None):
        """Monitorea cuanto tiempo lleva cada ave sin comer/beber.

        aves: lista de nombres (ej: ["Yukki", "Mushu"]). Si no se pasa,
        se monitorea un unico registro general.
        """
        now = time.time()
        self.aves = list(aves) if aves else ["General"]

        # ave -> timestamps de ultima comida/bebida. Cuando Azure SQL contiene
        # historial se restaura para no reiniciar artificialmente el contador.
        estado_inicial = estado_inicial or {}
        self.registro = {}
        for ave in self.aves:
            previo = estado_inicial.get(ave, {})
            self.registro[ave] = {
                "comer": self._timestamp_valido(previo.get("comer"), now),
                "beber": self._timestamp_valido(previo.get("beber"), now),
            }

        # Configuracion de umbrales (en segundos). 4 horas = 14400
        self.THRESHOLD_EATING = 14400
        self.THRESHOLD_DRINKING = 14400

    @staticmethod
    def _timestamp_valido(valor, ahora):
        """Acepta timestamps históricos, pero nunca fechas futuras o inválidas."""
        if not isinstance(valor, (int, float)) or valor < 0 or valor > ahora:
            return ahora
        return float(valor)

    def register_action(self, action, ave=None):
        """Actualiza los timestamps segun la accion detectada.

        Si no se pudo identificar al ave (ej: vision nocturna sin color),
        se actualizan todas: es preferible perder una alerta puntual a
        generar alertas falsas de un ave que si estaba comiendo.
        """
        if not action:
            return

        now = time.time()
        objetivos = [ave] if ave in self.registro else list(self.registro.keys())

        for a in objetivos:
            if "Alimentacion" in action:
                self.registro[a]["comer"] = now
            elif "Hidratacion" in action:
                self.registro[a]["beber"] = now

    def check_health(self):
        """Retorna una lista de alertas si se exceden los tiempos.

        Cada alerta es un dict con:
        - tipo: clave estable (ej: "sin_comer:Yukki"), util para no
          registrar la misma alerta dos veces en la base de datos.
        - ave: nombre del ave afectada.
        - texto: mensaje para mostrar en pantalla (sin emojis, OpenCV
          no los renderiza).
        - horas: tiempo transcurrido en horas.
        """
        alerts = []
        now = time.time()

        for ave, ts in self.registro.items():
            horas_comer = (now - ts["comer"]) / 3600
            horas_beber = (now - ts["beber"]) / 3600

            if (now - ts["comer"]) > self.THRESHOLD_EATING:
                alerts.append({
                    "tipo": f"sin_comer:{ave}",
                    "ave": ave,
                    "texto": f"! {ave.upper()} SIN COMER: {horas_comer:.1f}h",
                    "horas": horas_comer,
                })

            if (now - ts["beber"]) > self.THRESHOLD_DRINKING:
                alerts.append({
                    "tipo": f"sin_beber:{ave}",
                    "ave": ave,
                    "texto": f"! {ave.upper()} SIN BEBER: {horas_beber:.1f}h",
                    "horas": horas_beber,
                })

        return alerts

    def get_stats(self):
        """Peor caso entre todas las aves + detalle por ave."""
        now = time.time()
        eating = max(now - ts["comer"] for ts in self.registro.values())
        drinking = max(now - ts["beber"] for ts in self.registro.values())
        return {
            "eating_sec": eating,
            "drinking_sec": drinking,
            "por_ave": {
                ave: {
                    "eating_sec": now - ts["comer"],
                    "drinking_sec": now - ts["beber"],
                }
                for ave, ts in self.registro.items()
            },
        }
