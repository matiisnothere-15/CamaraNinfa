import time


class EstabilizadorAnimo:
    """Evita que el estado de ánimo 'parpadee' frame a frame.

    Un estado nuevo debe mantenerse durante `segundos_confirmacion`
    seguidos antes de reemplazar al estado oficial.
    """

    def __init__(self, segundos_confirmacion=10.0, estado_inicial="Normal"):
        self.segundos_confirmacion = segundos_confirmacion
        self.estado_oficial = estado_inicial
        self.estado_oficial_desde = time.time()
        self._candidato = estado_inicial
        self._candidato_desde = time.time()

    def actualizar(self, estado_instantaneo):
        """Recibe el estado calculado en este frame.

        Retorna (estado_oficial, cambio): `cambio` es True solo en el
        instante en que el estado oficial cambia (útil para guardar en BD).
        """
        ahora = time.time()

        if estado_instantaneo != self._candidato:
            self._candidato = estado_instantaneo
            self._candidato_desde = ahora

        cambio = False
        if (
            self._candidato != self.estado_oficial
            and (ahora - self._candidato_desde) >= self.segundos_confirmacion
        ):
            self.estado_oficial = self._candidato
            self.estado_oficial_desde = ahora
            cambio = True

        return self.estado_oficial, cambio

    def segundos_en_estado(self):
        return time.time() - self.estado_oficial_desde


class SnapshotPeriodico:
    """Cada `intervalo_segundos` arma un paquete de filas para la BD con
    el estado completo del sistema: ánimo, actividad, audio y salud.

    Con esto queda historial en Azure para estadísticas, recomendaciones
    y la futura app (no solo los eventos de comer/beber).
    """

    def __init__(self, intervalo_segundos=300):
        self.intervalo = intervalo_segundos
        # Se espera un intervalo completo antes del primer snapshot,
        # para que los monitores ya tengan datos reales.
        self.ultimo_snapshot = time.time()

    def toca_guardar(self):
        return (time.time() - self.ultimo_snapshot) >= self.intervalo

    def armar_filas(self, mood, move_status, move_val, audio_stats, health_stats):
        """Retorna la lista de filas (tuplas) listas para insertar_registros()."""
        self.ultimo_snapshot = time.time()

        horas_sin_comer = health_stats["eating_sec"] / 3600.0
        horas_sin_beber = health_stats["drinking_sec"] / 3600.0

        return [
            ("Snapshot", "EstadoAnimo", 0.0, mood, 1.0, ""),
            (
                "Snapshot",
                "Actividad",
                float(move_val),
                move_status,
                1.0,
                "%diagonal/min",
            ),
            (
                "Snapshot",
                "Audio",
                float(audio_stats["rms"]),
                audio_stats["status"],
                1.0,
                f"freq={audio_stats['freq']:.0f}Hz",
            ),
            (
                "Snapshot",
                "SinComer",
                round(horas_sin_comer, 2),
                "Alerta" if horas_sin_comer >= 4 else "OK",
                1.0,
                "horas",
            ),
            (
                "Snapshot",
                "SinBeber",
                round(horas_sin_beber, 2),
                "Alerta" if horas_sin_beber >= 4 else "OK",
                1.0,
                "horas",
            ),
        ]
