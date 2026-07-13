"""Auditoría reproducible del dataset YOLO del Monitor de Ninfas."""

from __future__ import annotations

import ast
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

EXTENSIONES_IMAGEN = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
SPLITS = ("train", "val", "test")


def leer_data_yaml(ruta: str | Path) -> dict:
    """Lee el subconjunto de YAML usado por la configuración del dataset."""
    ruta = Path(ruta).resolve()
    datos: dict = {"yaml_file": str(ruta)}
    nombres: dict[int, str] = {}
    en_nombres = False

    for numero, linea_original in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        linea = linea_original.split("#", 1)[0].rstrip()
        if not linea.strip():
            continue
        indentada = linea[:1].isspace()
        texto = linea.strip()
        if en_nombres and indentada:
            if ":" not in texto:
                raise ValueError(f"data.yaml:{numero}: entrada de clase inválida.")
            clave, valor = texto.split(":", 1)
            nombres[int(clave.strip())] = valor.strip().strip("'\"")
            continue
        en_nombres = False
        if ":" not in texto:
            continue
        clave, valor = texto.split(":", 1)
        clave, valor = clave.strip(), valor.strip()
        if clave == "names":
            if valor:
                lista = ast.literal_eval(valor)
                nombres = {indice: str(nombre) for indice, nombre in enumerate(lista)}
            else:
                en_nombres = True
        elif clave in {"path", "train", "val", "test"}:
            datos[clave] = valor.strip("'\"")
        elif clave == "nc":
            datos[clave] = int(valor)

    if nombres:
        indices = sorted(nombres)
        if indices != list(range(len(indices))):
            raise ValueError("Los índices de 'names' deben ser consecutivos desde cero.")
        datos["names"] = nombres
    if "names" not in datos:
        raise ValueError("data.yaml debe declarar el mapa de clases 'names'.")
    if datos.get("nc", len(nombres)) != len(nombres):
        raise ValueError("'nc' no coincide con la cantidad de clases declaradas.")
    return datos


def resolver_splits(datos: dict) -> dict[str, Path]:
    yaml_dir = Path(datos["yaml_file"]).parent
    raiz = Path(datos.get("path") or yaml_dir)
    if not raiz.is_absolute():
        raiz = yaml_dir / raiz
    resultado = {}
    for split in SPLITS:
        valor = datos.get(split)
        if valor:
            ruta = Path(valor)
            resultado[split] = (ruta if ruta.is_absolute() else raiz / ruta).resolve()
    return resultado


def _imagenes_de_split(ruta: Path) -> tuple[list[Path], bytes]:
    if ruta.is_dir():
        if ruta.name != "images":
            raise ValueError("la ruta debe terminar en una carpeta 'images'.")
        return (
            sorted(
                archivo
                for archivo in ruta.iterdir()
                if archivo.is_file() and archivo.suffix.lower() in EXTENSIONES_IMAGEN
            ),
            b"",
        )
    if ruta.is_file() and ruta.suffix.lower() == ".txt":
        contenido = ruta.read_text(encoding="utf-8")
        imagenes = []
        for numero, linea in enumerate(contenido.splitlines(), 1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if linea.startswith("./"):
                imagen = ruta.parent / linea[2:]
            else:
                imagen = Path(linea)
                if not imagen.is_absolute():
                    imagen = ruta.parent / imagen
            imagen = imagen.resolve()
            if imagen.suffix.lower() not in EXTENSIONES_IMAGEN:
                raise ValueError(f"línea {numero}: extensión de imagen no soportada.")
            imagenes.append(imagen)
        return sorted(imagenes), contenido.encode()
    raise ValueError("debe ser una carpeta de imágenes o un manifiesto .txt.")


def _etiqueta_de_imagen(imagen: Path) -> Path:
    if imagen.parent.name != "images":
        return imagen.with_suffix(".txt")
    return imagen.parent.parent / "labels" / f"{imagen.stem}.txt"


def _tipo_etiqueta(partes: list[str]) -> str | None:
    if len(partes) == 5:
        return "bbox"
    if len(partes) >= 7 and len(partes) % 2 == 1:
        return "polygon"
    return None


def _origen_roboflow(stem: str) -> str:
    return stem.split("_jpg.rf.", 1)[0]


def _dhash(imagen, lado: int = 16) -> int:
    gris = imagen.convert("L").resize((lado + 1, lado))
    obtener = getattr(gris, "get_flattened_data", gris.getdata)
    pixeles = list(obtener())
    return sum(
        1 << indice
        for indice in range(lado * lado)
        if pixeles[(indice // lado) * (lado + 1) + indice % lado]
        > pixeles[(indice // lado) * (lado + 1) + indice % lado + 1]
    )


def auditar_dataset(ruta_yaml: str | Path, umbral_similitud: int = 2) -> dict:
    from PIL import Image

    ruta_yaml = Path(ruta_yaml).resolve()
    datos = leer_data_yaml(ruta_yaml)
    rutas = resolver_splits(datos)
    errores: list[str] = []
    advertencias: list[str] = []
    resumen_splits: dict = {}
    todas_muestras = []
    clases_globales: Counter = Counter()
    formatos_globales: Counter = Counter()
    huella = hashlib.sha256()
    huella.update(ruta_yaml.read_bytes())

    for split in SPLITS:
        split_ruta = rutas.get(split)
        if split_ruta is None:
            if split in {"train", "val"}:
                errores.append(f"Falta la ruta obligatoria '{split}' en data.yaml.")
            continue
        if not split_ruta.exists():
            errores.append(f"No existe la fuente de imágenes de {split}: {split_ruta}")
            continue
        try:
            rutas_imagen, contenido_manifiesto = _imagenes_de_split(split_ruta)
        except ValueError as error:
            errores.append(f"{split}: {error}")
            continue
        huella.update(contenido_manifiesto)
        imagenes = {ruta.stem: ruta for ruta in rutas_imagen}
        if len(imagenes) != len(rutas_imagen):
            errores.append(f"{split}: hay nombres de imagen duplicados en el manifiesto.")
        etiquetas = {
            stem: _etiqueta_de_imagen(ruta)
            for stem, ruta in imagenes.items()
            if _etiqueta_de_imagen(ruta).is_file()
        }
        faltantes = sorted(set(imagenes) - set(etiquetas))
        huerfanas = []
        if split_ruta.is_dir():
            etiquetas_dir = split_ruta.parent / "labels"
            if etiquetas_dir.is_dir():
                todas_etiquetas = {ruta.stem for ruta in etiquetas_dir.glob("*.txt")}
                huerfanas = sorted(todas_etiquetas - set(imagenes))
        if faltantes:
            errores.append(f"{split}: {len(faltantes)} imágenes no tienen etiqueta.")
        if huerfanas:
            errores.append(f"{split}: {len(huerfanas)} etiquetas no tienen imagen.")

        conteo_clases: Counter = Counter()
        formatos: Counter = Counter()
        vacias = objetos = diminutas = 0
        dimensiones: Counter = Counter()

        for stem, imagen_ruta in sorted(imagenes.items()):
            etiqueta_ruta = etiquetas.get(stem)
            try:
                with Image.open(imagen_ruta) as imagen:
                    imagen.verify()
                with Image.open(imagen_ruta) as imagen:
                    ancho, alto = imagen.size
                    hash_perceptual = _dhash(imagen)
                dimensiones[f"{ancho}x{alto}"] += 1
            except Exception as error:
                errores.append(f"{split}/{imagen_ruta.name}: imagen corrupta ({error}).")
                continue

            digest = hashlib.sha256(imagen_ruta.read_bytes()).hexdigest()
            huella.update(imagen_ruta.name.encode())
            huella.update(bytes.fromhex(digest))
            todas_muestras.append(
                {
                    "split": split,
                    "archivo": imagen_ruta.name,
                    "sha256": digest,
                    "dhash": hash_perceptual,
                    "origen": _origen_roboflow(stem),
                }
            )
            if etiqueta_ruta is None:
                continue

            contenido = etiqueta_ruta.read_text(encoding="utf-8")
            huella.update(etiqueta_ruta.name.encode())
            huella.update(contenido.encode())
            lineas = [linea.strip() for linea in contenido.splitlines() if linea.strip()]
            if not lineas:
                vacias += 1
                continue
            if len(lineas) != len(set(lineas)):
                errores.append(f"{split}/{etiqueta_ruta.name}: contiene anotaciones duplicadas.")

            formatos_archivo = set()
            for numero, linea in enumerate(lineas, 1):
                partes = linea.split()
                formato = _tipo_etiqueta(partes)
                if formato is None:
                    errores.append(
                        f"{split}/{etiqueta_ruta.name}:{numero}: formato YOLO inválido."
                    )
                    continue
                formatos_archivo.add(formato)
                formatos[formato] += 1
                formatos_globales[formato] += 1
                try:
                    clase = int(partes[0])
                    coordenadas = [float(valor) for valor in partes[1:]]
                except ValueError:
                    errores.append(
                        f"{split}/{etiqueta_ruta.name}:{numero}: valor no numérico."
                    )
                    continue
                if clase not in datos["names"]:
                    errores.append(
                        f"{split}/{etiqueta_ruta.name}:{numero}: clase {clase} desconocida."
                    )
                    continue
                if not all(0 <= valor <= 1 for valor in coordenadas):
                    errores.append(
                        f"{split}/{etiqueta_ruta.name}:{numero}: coordenada fuera de [0, 1]."
                    )
                    continue

                if formato == "bbox":
                    _x, _y, ancho_n, alto_n = coordenadas
                    valido = ancho_n > 0 and alto_n > 0
                else:
                    xs, ys = coordenadas[0::2], coordenadas[1::2]
                    ancho_n, alto_n = max(xs) - min(xs), max(ys) - min(ys)
                    area = abs(
                        sum(
                            xs[i] * ys[(i + 1) % len(ys)]
                            - xs[(i + 1) % len(xs)] * ys[i]
                            for i in range(len(xs))
                        )
                        / 2
                    )
                    valido = ancho_n > 0 and alto_n > 0 and area > 1e-9
                if not valido:
                    errores.append(
                        f"{split}/{etiqueta_ruta.name}:{numero}: anotación degenerada."
                    )
                    continue
                if ancho_n * ancho < 2 or alto_n * alto < 2:
                    diminutas += 1
                conteo_clases[clase] += 1
                clases_globales[clase] += 1
                objetos += 1

            if len(formatos_archivo) > 1:
                errores.append(
                    f"{split}/{etiqueta_ruta.name}: mezcla cajas y polígonos en el mismo archivo."
                )

        if diminutas:
            advertencias.append(f"{split}: {diminutas} anotaciones miden menos de 2 píxeles.")
        resumen_splits[split] = {
            "imagenes": len(imagenes),
            "etiquetas": len(etiquetas),
            "imagenes_negativas": vacias,
            "objetos": objetos,
            "clases": {
                datos["names"][indice]: conteo_clases.get(indice, 0)
                for indice in datos["names"]
            },
            "formatos": dict(sorted(formatos.items())),
            "dimensiones": dict(sorted(dimensiones.items())),
        }

    por_hash: dict[str, list[dict]] = defaultdict(list)
    por_origen: dict[str, set[str]] = defaultdict(set)
    for muestra in todas_muestras:
        por_hash[muestra["sha256"]].append(muestra)
        por_origen[muestra["origen"]].add(muestra["split"])
    duplicados_exactos = [
        [f"{m['split']}/{m['archivo']}" for m in muestras]
        for muestras in por_hash.values()
        if len({m["split"] for m in muestras}) > 1
    ]
    fugas_origen = {
        origen: sorted(splits) for origen, splits in por_origen.items() if len(splits) > 1
    }
    if duplicados_exactos:
        errores.append(f"Hay {len(duplicados_exactos)} imágenes idénticas entre splits.")
    if fugas_origen:
        errores.append(f"Hay {len(fugas_origen)} imágenes fuente repetidas entre splits.")

    similares = []
    for indice, primera in enumerate(todas_muestras):
        for segunda in todas_muestras[indice + 1 :]:
            if primera["split"] == segunda["split"]:
                continue
            distancia = (primera["dhash"] ^ segunda["dhash"]).bit_count()
            if distancia <= umbral_similitud:
                similares.append(
                    {
                        "distancia": distancia,
                        "a": f"{primera['split']}/{primera['archivo']}",
                        "b": f"{segunda['split']}/{segunda['archivo']}",
                    }
                )
    similares.sort(key=lambda par: (par["distancia"], par["a"], par["b"]))
    if similares:
        advertencias.append(
            f"Hay {len(similares)} pares visualmente casi idénticos entre splits "
            f"(dHash <= {umbral_similitud}); las métricas pueden ser optimistas."
        )

    total_imagenes = sum(split["imagenes"] for split in resumen_splits.values())
    if total_imagenes < 300:
        advertencias.append(
            f"El dataset tiene solo {total_imagenes} imágenes; conviene ampliar escenarios y días."
        )
    if resumen_splits.get("test", {}).get("imagenes", 0) < 50:
        advertencias.append(
            "El test tiene menos de 50 imágenes; sus métricas tendrán alta varianza."
        )

    try:
        yaml_mostrado = ruta_yaml.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        yaml_mostrado = str(ruta_yaml)

    return {
        "ok": not errores,
        "data_yaml": yaml_mostrado,
        "tarea_objetivo": "detect",
        "tratamiento_etiquetas": (
            "Los polígonos YOLO se convierten a sus cajas envolventes durante "
            "el entrenamiento de detección."
        ),
        "huella_sha256": huella.hexdigest(),
        "clases": datos["names"],
        "splits": resumen_splits,
        "totales": {
            "imagenes": total_imagenes,
            "objetos": sum(clases_globales.values()),
            "clases": {
                datos["names"][indice]: clases_globales.get(indice, 0)
                for indice in datos["names"]
            },
            "formatos": dict(sorted(formatos_globales.items())),
        },
        "integridad": {
            "duplicados_exactos_entre_splits": duplicados_exactos,
            "fuentes_repetidas_entre_splits": fugas_origen,
            "pares_visualmente_similares": len(similares),
            "ejemplos_similares": similares[:20],
            "umbral_dhash": umbral_similitud,
        },
        "errores": errores,
        "advertencias": advertencias,
    }
