"""Audita integridad, anotaciones, balance y fugas entre splits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from modulos.dataset_audit import auditar_dataset


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=RAIZ / "entrenamiento" / "data.yaml")
    parser.add_argument("--salida", type=Path, help="Archivo JSON donde guardar el informe.")
    parser.add_argument("--umbral-similitud", type=int, default=2, choices=range(0, 17))
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    informe = auditar_dataset(args.data, umbral_similitud=args.umbral_similitud)
    serializado = json.dumps(informe, ensure_ascii=False, indent=2)
    print(serializado)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(serializado + "\n", encoding="utf-8")
        print(f"Informe guardado en: {args.salida}")
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
