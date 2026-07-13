"""Crea splits por fuente y similitud visual para reducir fuga temporal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _dhash(ruta: Path, lado: int = 16) -> int:
    with Image.open(ruta) as imagen:
        gris = imagen.convert("L").resize((lado + 1, lado))
        obtener = getattr(gris, "get_flattened_data", gris.getdata)
        pixeles = list(obtener())
    return sum(
        1 << indice
        for indice in range(lado * lado)
        if pixeles[(indice // lado) * (lado + 1) + indice % lado]
        > pixeles[(indice // lado) * (lado + 1) + indice % lado + 1]
    )


def _origen(stem: str) -> str:
    return stem.split("_jpg.rf.", 1)[0]


def _componentes(hashes: dict[str, list[int]], umbral: int) -> list[list[str]]:
    fuentes = sorted(hashes)
    padres = list(range(len(fuentes)))

    def raiz(indice):
        while padres[indice] != indice:
            padres[indice] = padres[padres[indice]]
            indice = padres[indice]
        return indice

    def unir(a, b):
        a, b = raiz(a), raiz(b)
        if a != b:
            padres[b] = a

    for indice, fuente in enumerate(fuentes):
        for anterior in range(indice):
            distancia = min(
                (primero ^ segundo).bit_count()
                for primero in hashes[fuente]
                for segundo in hashes[fuentes[anterior]]
            )
            if distancia <= umbral:
                unir(indice, anterior)
    grupos: dict[int, list[str]] = defaultdict(list)
    for indice, fuente in enumerate(fuentes):
        grupos[raiz(indice)].append(fuente)
    return list(grupos.values())


def _asignar(grupos: list[list[str]], seed: int) -> dict[str, str]:
    total = sum(map(len, grupos))
    objetivos = {
        "train": round(total * 0.70),
        "val": round(total * 0.15),
    }
    objetivos["test"] = total - objetivos["train"] - objetivos["val"]
    asignados = Counter()
    resultado = {}

    def desempate(grupo, split):
        texto = f"{seed}:{split}:{'|'.join(sorted(grupo))}".encode()
        return hashlib.sha256(texto).hexdigest()

    grupos = sorted(
        grupos,
        key=lambda grupo: (
            -len(grupo),
            hashlib.sha256(f"{seed}:{sorted(grupo)}".encode()).hexdigest(),
        ),
    )
    limite_grupo_evaluacion = max(2, min(objetivos["val"], objetivos["test"]) // 3)
    for grupo in grupos:
        if len(grupo) > limite_grupo_evaluacion:
            elegido = "train"
        else:
            posibles = [
                split
                for split in ("train", "val", "test")
                if asignados[split] + len(grupo) <= objetivos[split]
            ] or ["train", "val", "test"]
            elegido = max(
                posibles,
                key=lambda split: (
                    (objetivos[split] - asignados[split]) / max(1, objetivos[split]),
                    desempate(grupo, split),
                ),
            )
        asignados[elegido] += len(grupo)
        for fuente in grupo:
            resultado[fuente] = elegido
    return resultado


def argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=RAIZ / "entrenamiento")
    parser.add_argument("--raw", type=Path, default=RAIZ / "dataset" / "images")
    parser.add_argument("--salida", type=Path, default=RAIZ / "entrenamiento" / "splits")
    parser.add_argument("--umbral-similitud", type=int, default=2, choices=range(0, 17))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    variantes: dict[str, list[Path]] = defaultdict(list)
    for split_fisico in ("train", "valid", "test"):
        for ruta in (args.dataset / split_fisico / "images").glob("*"):
            if ruta.suffix.lower() in EXTENSIONES:
                variantes[_origen(ruta.stem)].append(ruta.resolve())
    if not variantes:
        print("No se encontraron imágenes exportadas.")
        return 1

    raw = {
        ruta.stem: ruta.resolve()
        for ruta in args.raw.glob("*")
        if ruta.suffix.lower() in EXTENSIONES
    }
    faltantes = sorted(set(variantes) - set(raw))
    if faltantes:
        print(f"Faltan {len(faltantes)} imágenes fuente en {args.raw}.")
        return 1

    hashes_raw = {fuente: _dhash(raw[fuente]) for fuente in variantes}
    hashes_variantes = {
        fuente: [_dhash(ruta) for ruta in rutas] for fuente, rutas in variantes.items()
    }
    grupos = _componentes(hashes_variantes, args.umbral_similitud)
    asignacion = _asignar(grupos, args.seed)
    manifiestos: dict[str, list[Path]] = defaultdict(list)
    fuentes_por_split: dict[str, list[str]] = defaultdict(list)

    for fuente, split in sorted(asignacion.items()):
        fuentes_por_split[split].append(fuente)
        opciones = sorted(variantes[fuente])
        if split == "train":
            manifiestos[split].extend(opciones)
        else:
            elegida = min(
                opciones,
                key=lambda ruta: ((hashes_raw[fuente] ^ _dhash(ruta)).bit_count(), str(ruta)),
            )
            manifiestos[split].append(elegida)

    args.salida.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        destino = args.salida / f"{split}.txt"
        if destino.exists() and not args.force:
            print(f"Ya existe {destino}; usa --force para regenerarlo.")
            return 1
        lineas = []
        for imagen in sorted(manifiestos[split]):
            relativa = os.path.relpath(imagen, args.salida.resolve()).replace("\\", "/")
            lineas.append(f"./{relativa}")
        destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    resumen = {
        "seed": args.seed,
        "umbral_dhash": args.umbral_similitud,
        "fuentes_totales": len(variantes),
        "componentes_similitud": len(grupos),
        "tamano_componentes": sorted((len(grupo) for grupo in grupos), reverse=True),
        "splits": {
            split: {
                "fuentes": len(fuentes_por_split[split]),
                "imagenes": len(manifiestos[split]),
                "ids_fuente": sorted(fuentes_por_split[split]),
            }
            for split in ("train", "val", "test")
        },
    }
    (args.salida / "manifest.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    resumen_corto = {
        split: resumen["splits"][split] | {"ids_fuente": "..."}
        for split in resumen["splits"]
    }
    print(json.dumps(resumen_corto, indent=2))
    print(f"Manifiestos generados en: {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
