"""Identificación exclusiva de ninfas por clase del detector RF-DETR y respaldo de color."""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict, deque

import cv2
import numpy as np

AVES_EXCLUIDAS: frozenset[str] = frozenset({"shiro"})
CLASES_MODELO_INDIVIDUALES: frozenset[str] = frozenset({"mushu", "yukki"})

PATRONES_TIPO = [
    ("amarilla", r"lutino"),
    ("blanca", r"albino"),
    ("gris", r"gris|plomo|silvestre|platead|oscur"),
    ("amarilla", r"amarill"),
    ("blanca", r"blanc"),
]

FRAC_AMARILLO = 0.22
FRAC_BLANCO = 0.45
FRAC_ACROMATICO = 0.45
MAX_AMARILLO_EN_GRIS = 0.08
FRAC_AMARILLO_CABEZA = 0.08
VALOR_GRIS_MAXIMO = 145
MIN_VOTOS = 8
MAYORIA = 0.70
MIN_VOTOS_MODELO = 2
MAYORIA_MODELO = 0.55
CONF_DIRECTA_MODELO = 0.65
SAT_FRAME_MINIMA = 12.0
MAX_EDAD_TRACK = 120.0


def es_ave_excluida(nombre: str | None) -> bool:
    if not nombre:
        return False
    return str(nombre).strip().lower() in AVES_EXCLUIDAS


class IdentificadorColor:
    """Asigna como máximo un track activo a cada ave registrada.

    Prioriza los votos de clase individual emitidos por RF-DETR (``mushu``,
    ``yukki``) y usa los votos cromáticos HSV como respaldo diurno (p. ej. si
    una detección cae en la clase histórica ``shiro``, que nunca se asigna ni
    alerta). ``resolver`` considera todos los tracks visibles a la vez, de modo
    que dos cajas no puedan recibir simultáneamente el nombre de Mushu o Yukki.
    """

    def __init__(self, historial: int = 60) -> None:
        self.historial = historial
        self.tipo_a_ave: dict[str, dict] = {}
        self.nombre_a_ave: dict[str, dict] = {}
        self.votos: dict[int, deque] = {}
        self.votos_modelo: dict[int, deque[tuple[str, float]]] = {}
        self.ultima_vez: dict[int, float] = {}
        self.color_disponible: dict[int, bool] = {}
        self.asignaciones: dict[int, tuple[int | None, str]] = {}
        self.activo = False

    @staticmethod
    def _construir_mapa_nombres(aves: list[dict]) -> dict[str, dict]:
        mapa: dict[str, dict] = {}
        for ave in aves:
            nombre = str(ave.get("nombre") or "").strip()
            clave = nombre.lower()
            if (
                not clave
                or clave in AVES_EXCLUIDAS
                or clave not in CLASES_MODELO_INDIVIDUALES
                or clave in mapa
            ):
                continue
            mapa[clave] = {"id": ave.get("id"), "nombre": nombre}
        return mapa

    @staticmethod
    def _construir_mapa_aves(aves: list[dict]) -> dict[str, dict]:
        mapa: dict[str, dict] = {}
        for ave in aves:
            if es_ave_excluida(ave.get("nombre")):
                continue
            # El color corporal manda sobre notas como "cara amarilla".
            # Elegir antes de deduplicar evita inventar otro tipo si está ocupado.
            coincidencias = (
                tipo
                for campo in ("color", "notas")
                for tipo, patron in PATRONES_TIPO
                if re.search(patron, (ave.get(campo) or "").lower())
            )
            tipo = next(coincidencias, None)
            if tipo is not None and tipo not in mapa:
                mapa[tipo] = {"id": ave.get("id"), "nombre": ave["nombre"]}
        return mapa

    def configurar(self, aves: list[dict]) -> bool:
        self.tipo_a_ave = self._construir_mapa_aves(aves)
        self.nombre_a_ave = self._construir_mapa_nombres(aves)
        self.votos.clear()
        self.votos_modelo.clear()
        self.ultima_vez.clear()
        self.color_disponible.clear()
        self.asignaciones.clear()
        self.activo = len(self.tipo_a_ave) >= 2 or len(self.nombre_a_ave) >= 2
        return self.activo

    def sincronizar_aves(self, aves: list[dict]) -> bool:
        """Actualiza aves en caliente sin borrar los votos acumulados."""
        nuevo_mapa = self._construir_mapa_aves(aves)
        nuevo_nombres = self._construir_mapa_nombres(aves)
        if len(nuevo_mapa) < 2 and len(nuevo_nombres) < 2:
            return False
        if nuevo_mapa == self.tipo_a_ave and nuevo_nombres == self.nombre_a_ave:
            return False
        self.tipo_a_ave = nuevo_mapa
        self.nombre_a_ave = nuevo_nombres
        self.activo = True
        self.asignaciones.clear()
        return True

    @staticmethod
    def frame_tiene_color(frame: np.ndarray) -> bool:
        if frame is None or frame.size == 0:
            return False
        muestra = frame[::8, ::8]
        hsv = cv2.cvtColor(muestra, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[:, :, 1])) >= SAT_FRAME_MINIMA

    @staticmethod
    def clasificar_color(
        frame: np.ndarray, coords: tuple[int, int, int, int]
    ) -> str | None:
        x1, y1, x2, y2 = coords
        alto_frame, ancho_frame = frame.shape[:2]
        x1 = max(0, min(ancho_frame, x1))
        x2 = max(0, min(ancho_frame, x2))
        y1 = max(0, min(alto_frame, y1))
        y2 = max(0, min(alto_frame, y2))
        if x2 <= x1 or y2 <= y1:
            return None

        margen_x = (x2 - x1) // 4
        margen_y = (y2 - y1) // 4
        recorte = frame[y1 + margen_y : y2 - margen_y, x1 + margen_x : x2 - margen_x]
        if recorte.size == 0:
            return None

        hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        validos = v > 40
        total = int(np.count_nonzero(validos))
        if total < 50:
            return None

        amarillo = np.count_nonzero(
            validos & (h >= 15) & (h <= 40) & (s > 70) & (v > 100)
        ) / total
        blanco = np.count_nonzero(validos & (s < 45) & (v > 185)) / total
        gris = np.count_nonzero(validos & (s < 55) & (v <= VALOR_GRIS_MAXIMO)) / total
        gris_medio = np.count_nonzero(
            validos & (s >= 18) & (s < 55) & (v <= 185)
        ) / total
        amarillo_suave_cuerpo = np.count_nonzero(
            validos & (h >= 15) & (h <= 40) & (s >= 20) & (v > 80)
        ) / total

        if amarillo >= FRAC_AMARILLO:
            if gris >= 0.35:
                return None  # Caja fusionada con evidencia de ambos plumajes.
            return "amarilla"

        # El centro de un lutino a contraluz puede verse gris y excluir la cara.
        # Muestrear también la parte superior permite ver amarillo poco saturado,
        # sin asumir que toda ave con cara amarilla tiene cuerpo lutino.
        ancho, alto = x2 - x1, y2 - y1
        cabeza = frame[
            y1 + int(alto * 0.03) : y1 + int(alto * 0.40),
            x1 + int(ancho * 0.08) : x2 - int(ancho * 0.08),
        ]
        cabeza_amarilla = False
        if cabeza.size:
            hsv_cabeza = cv2.cvtColor(cabeza, cv2.COLOR_BGR2HSV)
            hc, sc, vc = (hsv_cabeza[:, :, i] for i in range(3))
            total_cabeza = int(np.count_nonzero(vc > 40))
            if total_cabeza >= 50:
                calidos = (hc >= 15) & (hc <= 40) & (vc > 80)
                suave = np.count_nonzero(calidos & (sc >= 20)) / total_cabeza
                marcado = np.count_nonzero(calidos & (sc >= 35)) / total_cabeza
                cabeza_amarilla = (
                    suave >= FRAC_AMARILLO_CABEZA
                    and marcado >= 0.05
                    and suave - amarillo_suave_cuerpo >= 0.05
                )
        if cabeza_amarilla:
            cuerpo_claro = np.count_nonzero(validos & (v > VALOR_GRIS_MAXIMO)) / total
            if cuerpo_claro >= 0.65 and gris <= 0.25:
                return "amarilla"
            # Cara amarilla con cuerpo oscuro puede ser gris o lutino en sombra.
            # No convertir esa ambigüedad en una identidad individual.
            return None

        if blanco >= FRAC_BLANCO and amarillo <= MAX_AMARILLO_EN_GRIS:
            return "blanca"
        if (
            max(gris, gris_medio) >= FRAC_ACROMATICO
            and amarillo <= MAX_AMARILLO_EN_GRIS
        ):
            return "gris"
        return None

    def resolver_clase_directa(
        self, nombre_clase: str | None
    ) -> tuple[int | None, str | None]:
        """Devuelve (ave_id, nombre) para una clase individual viva sin tracker."""
        if not nombre_clase:
            return (None, None)
        clave = str(nombre_clase).strip().lower()
        if clave in AVES_EXCLUIDAS:
            return (None, None)
        ave = self.nombre_a_ave.get(clave)
        if ave is None:
            return (None, None)
        return (ave["id"], ave["nombre"])

    def registrar_voto_modelo(
        self,
        track_id: int,
        nombre_clase: str | None,
        confianza: float = 1.0,
        ahora: float | None = None,
    ) -> bool:
        """Registra un voto del detector RF-DETR; 'shiro' entra como ambiguo."""
        if not self.activo or track_id is None:
            return False
        ahora = time.monotonic() if ahora is None else ahora
        self.limpiar(ahora)
        clave = str(nombre_clase or "").strip().lower()
        votos = self.votos_modelo.setdefault(track_id, deque(maxlen=self.historial))
        self.ultima_vez[track_id] = ahora
        if not clave or clave in AVES_EXCLUIDAS or clave not in self.nombre_a_ave:
            votos.append(("__ambiguo__", float(confianza)))
            return False
        ultimo_valido = next(
            (c for c, _conf in reversed(votos) if c in self.nombre_a_ave), None
        )
        if ultimo_valido is not None and ultimo_valido != clave:
            votos.clear()
            self.asignaciones.pop(track_id, None)
        votos.append((clave, float(confianza)))
        return True

    def registrar_voto(self, track_id: int, tipo: str, ahora: float | None = None) -> None:
        """Registra un voto ya clasificado; también facilita pruebas deterministas."""
        if not self.activo or tipo not in self.tipo_a_ave:
            return
        ahora = time.monotonic() if ahora is None else ahora
        votos = self.votos.setdefault(track_id, deque(maxlen=self.historial))
        votos.append(tipo)
        self.ultima_vez[track_id] = ahora
        self.color_disponible[track_id] = True

    def _suspender_color(self, track_id: int, ahora: float | None = None) -> None:
        """Limpia únicamente votos HSV cuando falta color o hay contradicción cromática."""
        if track_id is None:
            return
        self.votos.pop(track_id, None)
        if track_id not in self.votos_modelo:
            self.asignaciones.pop(track_id, None)
        self.color_disponible[track_id] = False
        self.ultima_vez[track_id] = time.monotonic() if ahora is None else ahora

    def suspender(self, track_id: int, ahora: float | None = None) -> None:
        """Retira el nombre y exige votos nuevos después de mezcla u oclusión."""
        if track_id is None:
            return
        self.votos.pop(track_id, None)
        self.votos_modelo.pop(track_id, None)
        self.asignaciones.pop(track_id, None)
        self.color_disponible[track_id] = False
        self.ultima_vez[track_id] = time.monotonic() if ahora is None else ahora

    def votar(
        self,
        track_id: int,
        frame: np.ndarray,
        coords: tuple[int, int, int, int],
        ahora: float | None = None,
    ) -> str | None:
        if not self.activo or track_id is None:
            return None
        ahora = time.monotonic() if ahora is None else ahora
        self.limpiar(ahora)
        self.ultima_vez[track_id] = ahora

        if not self.frame_tiene_color(frame):
            self._suspender_color(track_id, ahora)
            return None

        tipo = self.clasificar_color(frame, coords)
        if tipo not in self.tipo_a_ave:
            self._suspender_color(track_id, ahora)
            return tipo
        votos = self.votos.get(track_id)
        if votos and votos[-1] != tipo:
            # Un ID del tracker puede pasar de un ave a otra al cruzarse.
            self._suspender_color(track_id, ahora)
        self.registrar_voto(track_id, tipo, ahora)
        return tipo

    def votar_deteccion(
        self,
        track_id: int,
        nombre_clase: str | None,
        frame: np.ndarray,
        coords: tuple[int, int, int, int],
        confianza: float = 1.0,
        ahora: float | None = None,
    ) -> str | None:
        """Combina el voto directo del detector RF-DETR con el respaldo HSV diurno."""
        if not self.activo or track_id is None:
            return None
        ahora = time.monotonic() if ahora is None else ahora
        self.registrar_voto_modelo(
            track_id, nombre_clase, confianza=confianza, ahora=ahora
        )
        return self.votar(track_id, frame, coords, ahora=ahora)

    def _candidatura_modelo(self, track_id: int):
        votos = self.votos_modelo.get(track_id)
        if not votos:
            return None
        conteo: Counter[str] = Counter(
            clave for clave, _conf in votos if clave in self.nombre_a_ave
        )
        if not conteo:
            return None
        clave, cantidad = conteo.most_common(1)[0]
        total = len(votos)
        proporcion = cantidad / total
        conf_media = sum(conf for c, conf in votos if c == clave) / cantidad
        confirmado = (
            total >= MIN_VOTOS_MODELO and proporcion >= MAYORIA_MODELO
        ) or (total == 1 and cantidad == 1 and conf_media >= CONF_DIRECTA_MODELO)
        if not confirmado:
            return None
        ave = self.nombre_a_ave[clave]
        puntuacion = (
            2,
            proporcion,
            conf_media,
            cantidad,
            self.ultima_vez.get(track_id, 0.0),
            -track_id,
        )
        return clave, ave, puntuacion

    def _candidatura(self, track_id: int):
        votos = self.votos.get(track_id)
        if (
            not votos
            or len(votos) < MIN_VOTOS
            or not self.color_disponible.get(track_id, False)
        ):
            return None
        tipo, cantidad = Counter(votos).most_common(1)[0]
        proporcion = cantidad / len(votos)
        if proporcion < MAYORIA or tipo not in self.tipo_a_ave:
            return None
        ave = self.tipo_a_ave[tipo]
        clave = str(ave["nombre"]).strip().lower()
        puntuacion = (
            1,
            proporcion,
            0.0,
            cantidad,
            self.ultima_vez.get(track_id, 0.0),
            -track_id,
        )
        return clave, ave, puntuacion

    def limpiar(self, ahora: float | None = None) -> None:
        ahora = time.monotonic() if ahora is None else ahora
        antiguos = [
            track_id
            for track_id, ultima in self.ultima_vez.items()
            if (ahora - ultima) > MAX_EDAD_TRACK
        ]
        for track_id in antiguos:
            self.votos.pop(track_id, None)
            self.votos_modelo.pop(track_id, None)
            self.ultima_vez.pop(track_id, None)
            self.color_disponible.pop(track_id, None)
            self.asignaciones.pop(track_id, None)

    def resolver(
        self, track_ids: list[int] | None = None, ahora: float | None = None
    ) -> dict[int, tuple[int | None, str]]:
        """Resuelve identidades de forma conjunta y exclusiva."""
        ahora = time.monotonic() if ahora is None else ahora
        self.limpiar(ahora)
        activos = (
            (set(self.votos) | set(self.votos_modelo))
            if track_ids is None
            else set(track_ids)
        )
        por_ave = defaultdict(list)

        for track_id in activos:
            candidatura = self._candidatura_modelo(track_id)
            if candidatura is None:
                candidatura = self._candidatura(track_id)
            if candidatura is not None:
                clave_ave, ave, puntuacion = candidatura
                por_ave[clave_ave].append((puntuacion, track_id, ave))

        asignaciones = {}
        for _clave_ave, candidatos in por_ave.items():
            _puntuacion, ganador, ave = max(candidatos, key=lambda item: item[0])
            asignaciones[ganador] = (ave["id"], ave["nombre"])

        self.asignaciones = asignaciones
        return dict(asignaciones)

    def identificar(self, track_id: int) -> tuple[int | None, str | None]:
        return self.asignaciones.get(track_id, (None, None))
