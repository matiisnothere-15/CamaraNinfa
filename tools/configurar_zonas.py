"""Selecciona una zona sobre un frame y genera su variable de entorno."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from modulos.fuente_video import (  # noqa: E402
    abrir_fuente_video,
    cargar_entorno,
    describir_fuente,
    resolver_fuente,
)


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuente", help="Índice de webcam o URL de video.")
    parser.add_argument(
        "--zona",
        choices=("comedero", "bebedero"),
        required=True,
        help="Nombre de la zona que se configurará.",
    )
    return parser.parse_args()


def seleccionar_puntos(frame) -> list[tuple[int, int]]:
    ventana = "Configurador de zonas"
    puntos: list[tuple[int, int]] = []
    base = frame.copy()

    def al_click(evento, x, y, _flags, _param):
        if evento == cv2.EVENT_LBUTTONDOWN:
            puntos.append((x, y))

    cv2.namedWindow(ventana)
    cv2.setMouseCallback(ventana, al_click)
    print("Haz clic en al menos 3 vértices; r reinicia y q termina.")
    while True:
        vista = base.copy()
        for indice, punto in enumerate(puntos):
            cv2.circle(vista, punto, 5, (0, 0, 255), -1)
            if indice:
                cv2.line(vista, puntos[indice - 1], punto, (0, 255, 255), 2)
        if len(puntos) >= 3:
            cv2.line(vista, puntos[-1], puntos[0], (0, 255, 255), 2)
        cv2.imshow(ventana, vista)
        tecla = cv2.waitKey(20) & 0xFF
        if tecla == ord("r"):
            puntos.clear()
        elif tecla == ord("q"):
            break
    cv2.destroyWindow(ventana)
    return puntos


def normalizar(puntos: list[tuple[int, int]], ancho: int, alto: int) -> str:
    if len(puntos) < 3:
        raise ValueError("La zona necesita al menos tres puntos.")
    if ancho <= 0 or alto <= 0:
        raise ValueError("El frame tiene dimensiones inválidas.")
    return ";".join(f"{x / ancho:.6f},{y / alto:.6f}" for x, y in puntos)


def main() -> int:
    opciones = argumentos()
    cargar_entorno(RAIZ / ".env")
    try:
        fuente = resolver_fuente(opciones.fuente)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    captura = abrir_fuente_video(fuente)
    try:
        correcto, frame = captura.read()
    finally:
        captura.release()
    if not correcto or frame is None:
        print(f"No se pudo leer {describir_fuente(fuente)}.", file=sys.stderr)
        return 1

    puntos = seleccionar_puntos(frame)
    try:
        valor = normalizar(puntos, frame.shape[1], frame.shape[0])
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"ZONA_{opciones.zona.upper()}={valor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
