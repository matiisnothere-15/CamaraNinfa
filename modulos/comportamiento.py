"""Máquina de estados temporal e independiente para cada ave rastreada."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class EstadoComportamiento(str, Enum):
    DESCONOCIDO = "DESCONOCIDO"
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    COMIENDO = "COMIENDO"
    BEBIENDO = "BEBIENDO"


class TipoEvento(str, Enum):
    INICIO = "Inicio"
    FIN = "Fin"


ACCION_BD = {
    EstadoComportamiento.ACTIVO: ("Comportamiento", "Movimiento"),
    EstadoComportamiento.INACTIVO: ("Comportamiento", "Inactividad"),
    EstadoComportamiento.COMIENDO: ("Accion", "Alimentacion"),
    EstadoComportamiento.BEBIENDO: ("Accion", "Hidratacion"),
}


@dataclass(slots=True)
class ObservacionComportamiento:
    track_id: int
    estado: EstadoComportamiento
    confianza: float
    ave_id: int | None = None
    nombre_ave: str | None = None


@dataclass(slots=True)
class EventoComportamiento:
    track_id: int
    estado: EstadoComportamiento
    tipo: TipoEvento
    timestamp: float
    duracion: float
    confianza: float
    ave_id: int | None
    nombre_ave: str | None
    motivo: str

    @property
    def categoria_bd(self) -> str:
        return ACCION_BD[self.estado][0]

    @property
    def accion_bd(self) -> str:
        return ACCION_BD[self.estado][1]


@dataclass(slots=True)
class EstadoTrack:
    track_id: int
    estado: EstadoComportamiento = EstadoComportamiento.DESCONOCIDO
    estado_desde: float = 0.0
    candidato: EstadoComportamiento = EstadoComportamiento.DESCONOCIDO
    candidato_desde: float = 0.0
    ultima_vez_visto: float = 0.0
    confianza: float = 0.0
    ave_id: int | None = None
    nombre_ave: str | None = None
    _identidad_confirmada: tuple[int | None, str | None] | None = field(
        default=None, repr=False
    )


@dataclass(slots=True)
class ConfiguracionComportamiento:
    confirmar_activo: float = 1.0
    confirmar_inactivo: float = 10.0
    confirmar_comiendo: float = 2.0
    confirmar_bebiendo: float = 2.0
    confirmar_salida_consumo: float = 6.0
    tolerancia_perdida: float = 3.0

    def umbral(self, estado: EstadoComportamiento) -> float:
        return {
            EstadoComportamiento.ACTIVO: self.confirmar_activo,
            EstadoComportamiento.INACTIVO: self.confirmar_inactivo,
            EstadoComportamiento.COMIENDO: self.confirmar_comiendo,
            EstadoComportamiento.BEBIENDO: self.confirmar_bebiendo,
        }.get(estado, float("inf"))


@dataclass
class GestorComportamiento:
    configuracion: ConfiguracionComportamiento = field(
        default_factory=ConfiguracionComportamiento
    )
    tracks: dict[int, EstadoTrack] = field(default_factory=dict)

    @staticmethod
    def _actualizar_identidad(
        track: EstadoTrack, observacion: ObservacionComportamiento
    ) -> None:
        track.confianza = observacion.confianza
        track.ave_id = observacion.ave_id
        track.nombre_ave = observacion.nombre_ave
        if observacion.ave_id is not None or observacion.nombre_ave is not None:
            # Se conserva solo para detectar reutilización del track; los
            # eventos y el resumen siguen usando la identidad visible actual.
            track._identidad_confirmada = (observacion.ave_id, observacion.nombre_ave)

    @staticmethod
    def _cambio_de_propietario(
        track: EstadoTrack, observacion: ObservacionComportamiento
    ) -> bool:
        anterior = track._identidad_confirmada
        if anterior is None:
            return False
        ave_id, nombre = anterior
        if ave_id is not None and observacion.ave_id is not None:
            return ave_id != observacion.ave_id
        if nombre is not None and observacion.nombre_ave is not None:
            return nombre.casefold() != observacion.nombre_ave.casefold()
        return False

    @staticmethod
    def _evento(
        track: EstadoTrack,
        estado: EstadoComportamiento,
        tipo: TipoEvento,
        timestamp: float,
        duracion: float,
        motivo: str,
    ) -> EventoComportamiento:
        return EventoComportamiento(
            track_id=track.track_id,
            estado=estado,
            tipo=tipo,
            timestamp=timestamp,
            duracion=max(0.0, duracion),
            confianza=track.confianza,
            ave_id=track.ave_id,
            nombre_ave=track.nombre_ave,
            motivo=motivo,
        )

    def _transicionar(
        self,
        track: EstadoTrack,
        nuevo_estado: EstadoComportamiento,
        momento: float,
    ) -> list[EventoComportamiento]:
        eventos = []
        estado_anterior = track.estado

        if estado_anterior in ACCION_BD:
            eventos.append(
                self._evento(
                    track,
                    estado_anterior,
                    TipoEvento.FIN,
                    momento,
                    momento - track.estado_desde,
                    "cambio_estado",
                )
            )

        track.estado = nuevo_estado
        track.estado_desde = momento
        track.candidato = nuevo_estado
        track.candidato_desde = momento

        if nuevo_estado in ACCION_BD:
            eventos.append(
                self._evento(
                    track,
                    nuevo_estado,
                    TipoEvento.INICIO,
                    momento,
                    0.0,
                    "confirmado",
                )
            )
        return eventos

    def _actualizar_track(
        self,
        track: EstadoTrack,
        observacion: ObservacionComportamiento,
        ahora: float,
    ) -> list[EventoComportamiento]:
        cambio_identidad = self._cambio_de_propietario(track, observacion)
        eventos = []
        if cambio_identidad:
            # Cierra antes de sobrescribir el dueño. Si estaba oculto, el FIN
            # queda anónimo y nunca hereda el nombre del ave recién recuperada.
            eventos = self._cerrar_track(
                track, track.ultima_vez_visto, "cambio_identidad"
            )
            track.estado = EstadoComportamiento.DESCONOCIDO
            track.estado_desde = ahora
            track.candidato = observacion.estado
            track.candidato_desde = ahora
        track.ultima_vez_visto = ahora
        self._actualizar_identidad(track, observacion)
        if cambio_identidad:
            return eventos

        # Sin evidencia suficiente se conserva el estado confirmado, pero se
        # cancela una transición que todavía estaba pendiente.
        if observacion.estado == EstadoComportamiento.DESCONOCIDO:
            track.candidato = track.estado
            track.candidato_desde = ahora
            return []

        if observacion.estado == track.estado:
            track.candidato = track.estado
            track.candidato_desde = ahora
            return []

        if observacion.estado != track.candidato:
            track.candidato = observacion.estado
            track.candidato_desde = ahora
            return []

        umbral = self.configuracion.umbral(observacion.estado)
        if track.estado in {
            EstadoComportamiento.COMIENDO,
            EstadoComportamiento.BEBIENDO,
        } and observacion.estado not in {
            EstadoComportamiento.COMIENDO,
            EstadoComportamiento.BEBIENDO,
        }:
            umbral = max(umbral, self.configuracion.confirmar_salida_consumo)
        if (ahora - track.candidato_desde) < umbral:
            return []

        return self._transicionar(
            track,
            observacion.estado,
            track.candidato_desde,
        )

    def _cerrar_track(
        self, track: EstadoTrack, momento: float, motivo: str
    ) -> list[EventoComportamiento]:
        if track.estado not in ACCION_BD:
            return []
        return [
            self._evento(
                track,
                track.estado,
                TipoEvento.FIN,
                momento,
                momento - track.estado_desde,
                motivo,
            )
        ]

    def actualizar(
        self,
        observaciones: list[ObservacionComportamiento],
        ahora: float | None = None,
    ) -> list[EventoComportamiento]:
        """Actualiza todos los tracks y devuelve solamente transiciones nuevas."""
        if ahora is None:
            ahora = time.monotonic()
        por_track = {}
        for observacion in observaciones:
            anterior = por_track.get(observacion.track_id)
            if anterior is None or observacion.confianza > anterior.confianza:
                por_track[observacion.track_id] = observacion

        eventos = []
        vistos = set(por_track)
        for track_id, observacion in por_track.items():
            track = self.tracks.get(track_id)
            if track is None:
                track = EstadoTrack(
                    track_id=track_id,
                    candidato=observacion.estado,
                    candidato_desde=ahora,
                    ultima_vez_visto=ahora,
                )
                self._actualizar_identidad(track, observacion)
                self.tracks[track_id] = track
                continue
            eventos.extend(self._actualizar_track(track, observacion, ahora))

        for track_id, track in list(self.tracks.items()):
            if track_id in vistos:
                continue
            if (ahora - track.ultima_vez_visto) <= self.configuracion.tolerancia_perdida:
                continue
            eventos.extend(
                self._cerrar_track(track, track.ultima_vez_visto, "track_perdido")
            )
            del self.tracks[track_id]

        return eventos

    def cerrar_todos(
        self, ahora: float | None = None, motivo: str = "cierre_monitor"
    ) -> list[EventoComportamiento]:
        if ahora is None:
            ahora = time.monotonic()
        eventos = []
        for track in self.tracks.values():
            momento = min(ahora, track.ultima_vez_visto)
            eventos.extend(self._cerrar_track(track, momento, motivo))
        self.tracks.clear()
        return eventos

    def resumen(self) -> str:
        partes = []
        for track_id in sorted(self.tracks):
            track = self.tracks[track_id]
            if track.estado == EstadoComportamiento.DESCONOCIDO:
                continue
            nombre = track.nombre_ave or f"#{track_id}"
            partes.append(f"{nombre}: {track.estado.value}")
        return " | ".join(partes)
