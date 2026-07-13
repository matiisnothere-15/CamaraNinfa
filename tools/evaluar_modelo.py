"""Evalúa un detector en val/test y genera un informe JSON trazable."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from modulos.dataset_audit import auditar_dataset
from modulos.metricas_modelo import extraer_metricas_deteccion


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modelo", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=RAIZ / "entrenamiento" / "data.yaml")
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--project", type=Path, default=RAIZ / "runs" / "evaluacion")
    parser.add_argument("--name", default=None)
    parser.add_argument("--salida", type=Path, help="Ruta opcional del JSON de métricas.")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if not args.modelo.is_file():
        print(f"No existe el modelo: {args.modelo}")
        return 1
    informe_dataset = auditar_dataset(args.data)
    if not informe_dataset["ok"]:
        print("El dataset no superó la auditoría; se cancela la evaluación.")
        return 1

    try:
        import ultralytics
        from ultralytics import YOLO
    except ImportError:
        print("Falta ultralytics. Instala primero las dependencias del proyecto.")
        return 1

    modelo = YOLO(str(args.modelo.resolve()))
    if getattr(modelo, "task", None) != "detect":
        print("Este evaluador requiere un modelo de detección.")
        return 1

    nombre_run = args.name or f"{args.modelo.stem}_{args.split}"
    opciones = {
        "data": str(args.data.resolve()),
        "split": args.split,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "project": str(args.project.resolve()),
        "name": nombre_run,
        "exist_ok": False,
        "plots": True,
        "verbose": True,
    }
    if args.device != "auto":
        opciones["device"] = args.device
    metricas = modelo.val(**opciones)

    reporte = {
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "modelo": {
            "archivo": str(args.modelo),
            "sha256": hashlib.sha256(args.modelo.read_bytes()).hexdigest(),
            "tarea": modelo.task,
        },
        "dataset": {
            "archivo": informe_dataset["data_yaml"],
            "huella_sha256": informe_dataset["huella_sha256"],
            "split": args.split,
            "resumen": informe_dataset["splits"][args.split],
            "advertencias": informe_dataset["advertencias"],
        },
        "entorno": {
            "python": platform.python_version(),
            "ultralytics": ultralytics.__version__,
        },
        "configuracion": {
            "imgsz": args.imgsz,
            "batch": args.batch,
            "device": args.device,
        },
        "metricas": extraer_metricas_deteccion(metricas.box, modelo.names),
        "velocidad_ms": {
            clave: float(valor) if valor is not None else None
            for clave, valor in metricas.speed.items()
        },
    }
    directorio_run = Path(metricas.save_dir)
    salida = args.salida or directorio_run / "metricas.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(reporte, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reporte["metricas"], ensure_ascii=False, indent=2))
    print(f"Informe completo: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
