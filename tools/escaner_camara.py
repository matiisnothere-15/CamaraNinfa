"""Prueba una URL configurada o busca webcams locales disponibles."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from modulos.fuente_video import (  # noqa: E402
    cargar_entorno,
    describir_fuente,
    resolver_fuente,
)


def probar(fuente: str | int, mostrar: bool = True) -> bool:
    captura = cv2.VideoCapture(fuente)
    try:
        correcto, frame = captura.read()
        if not captura.isOpened() or not correcto or frame is None:
            return False
        if not mostrar:
            return True

        print(f"Conexión exitosa: {describir_fuente(fuente)}. Presiona q para salir.")
        while correcto and frame is not None:
            cv2.imshow("Prueba de cámara", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            correcto, frame = captura.read()
        return True
    finally:
        captura.release()
        cv2.destroyAllWindows()


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fuente", help="Índice de webcam o URL de video.")
    parser.add_argument("--max-webcams", type=int, default=5)
    parser.add_argument("--sin-vista", action="store_true")
    parser.add_argument(
        "--escanear",
        action="store_true",
        help="Ignora .env y prueba los índices locales desde cero.",
    )
    return parser.parse_args()


def main() -> int:
    opciones = argumentos()
    cargar_entorno(RAIZ / ".env")
    if opciones.max_webcams <= 0:
        print("Error: --max-webcams debe ser mayor que cero.", file=sys.stderr)
        return 1

    if opciones.escanear:
        encontradas = []
        for indice in range(opciones.max_webcams):
            if probar(indice, mostrar=False):
                encontradas.append(indice)
                print(f"Webcam disponible: {indice}")
        if not encontradas:
            print("No se encontraron webcams locales.", file=sys.stderr)
            return 1
        if not opciones.sin_vista:
            probar(encontradas[0], mostrar=True)
        return 0

    try:
        fuente = resolver_fuente(opciones.fuente)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if probar(fuente, mostrar=not opciones.sin_vista):
        if opciones.sin_vista:
            print(f"Conexión exitosa: {describir_fuente(fuente)}")
        return 0
    print(f"No se pudo leer {describir_fuente(fuente)}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
