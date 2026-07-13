"""Captura imágenes limpias y espaciadas para ampliar el dataset."""

from __future__ import annotations

import argparse
import sys
import time
import uuid
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


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fuente",
        help="Índice de webcam o URL; si se omite usa .env/CAMARA_PC_INDICE.",
    )
    parser.add_argument("--destino", type=Path, default=RAIZ / "dataset" / "images")
    parser.add_argument("--intervalo", type=float, default=5.0, help="Segundos entre fotos.")
    parser.add_argument("--total", type=int, default=50, help="Cantidad máxima de fotos.")
    return parser.parse_args()


def recolectar(
    fuente: str | int,
    destino: Path,
    intervalo: float,
    total: int,
) -> int:
    if intervalo <= 0 or total <= 0:
        raise ValueError("--intervalo y --total deben ser mayores que cero.")

    destino.mkdir(parents=True, exist_ok=True)
    captura = cv2.VideoCapture(fuente)
    if not captura.isOpened():
        raise RuntimeError(f"No se pudo abrir {describir_fuente(fuente)}.")

    print(f"Fuente: {describir_fuente(fuente)}")
    print(f"Destino: {destino.resolve()}")
    print("Presiona q para terminar antes.")
    contador = 0
    ultima_captura = time.monotonic() - intervalo

    try:
        while contador < total:
            correcto, frame = captura.read()
            if not correcto or frame is None:
                raise RuntimeError("La fuente dejó de entregar imágenes.")

            ahora = time.monotonic()
            restante = max(0.0, intervalo - (ahora - ultima_captura))
            vista = frame.copy()
            cv2.putText(
                vista,
                f"Foto {contador + 1}/{total} | Proxima: {restante:.1f}s",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
            )

            if ahora - ultima_captura >= intervalo:
                nombre = f"ninfa_{uuid.uuid4().hex[:12]}.jpg"
                ruta = destino / nombre
                if not cv2.imwrite(str(ruta), frame):
                    raise RuntimeError(f"OpenCV no pudo guardar {ruta}.")
                contador += 1
                ultima_captura = ahora
                print(f"Guardada ({contador}/{total}): {nombre}")

            cv2.imshow("Recolector de dataset", vista)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        captura.release()
        cv2.destroyAllWindows()

    return contador


def main() -> int:
    opciones = argumentos()
    cargar_entorno(RAIZ / ".env")
    try:
        fuente = resolver_fuente(opciones.fuente)
        cantidad = recolectar(
            fuente,
            opciones.destino,
            opciones.intervalo,
            opciones.total,
        )
    except (RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Sesión terminada: {cantidad} fotos guardadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
