"""Entrena un detector YOLOv8 de forma reproducible para el Monitor de Ninfas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from modulos.dataset_audit import auditar_dataset


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=RAIZ / "entrenamiento" / "data.yaml")
    parser.add_argument("--modelo", default=str(RAIZ / "yolov8n.pt"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--cache", choices=("no", "ram", "disk"), default="no")
    parser.add_argument("--project", type=Path, default=RAIZ / "runs" / "entrenamiento")
    parser.add_argument("--name", default="yolov8n_ninfas_512_seed42")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    for nombre in ("epochs", "imgsz", "batch", "patience"):
        if getattr(args, nombre) <= 0:
            raise SystemExit(f"--{nombre} debe ser mayor que cero.")

    informe = auditar_dataset(args.data)
    if not informe["ok"]:
        print("El dataset no superó la auditoría:")
        for error in informe["errores"]:
            print(f"- {error}")
        return 1
    for advertencia in informe["advertencias"]:
        print(f"ADVERTENCIA: {advertencia}")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Falta ultralytics. Instala primero las dependencias del proyecto.")
        return 1

    modelo = YOLO(args.modelo)
    if getattr(modelo, "task", None) != "detect":
        print("El checkpoint inicial debe ser un modelo de detección, no de segmentación.")
        return 1

    opciones = {
        "data": str(args.data.resolve()),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "patience": args.patience,
        "workers": args.workers,
        "seed": args.seed,
        "deterministic": True,
        "cache": False if args.cache == "no" else args.cache,
        "project": str(args.project.resolve()),
        "name": args.name,
        "exist_ok": False,
        "plots": True,
        "save": True,
        "save_period": 10,
        "close_mosaic": 10,
    }
    if args.device != "auto":
        opciones["device"] = args.device

    modelo.train(**opciones)
    salida = Path(modelo.trainer.save_dir)
    print(f"Entrenamiento finalizado: {salida}")
    print(f"Mejor checkpoint: {salida / 'weights' / 'best.pt'}")
    print("Evalúalo en test con tools/evaluar_modelo.py antes de reemplazar best.pt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
