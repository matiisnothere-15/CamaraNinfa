"""Verificación liviana del proyecto sin abrir cámara ni conectar servicios.

Uso:
    python tools/verificar_proyecto.py

El comando comprueba sintaxis, archivos esenciales y disponibilidad de las
dependencias directas. Devuelve código 1 si encuentra un bloqueo.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

ARCHIVOS_ESENCIALES = (
    "main.py",
    "best.pt",
    "requirements.txt",
    ".env.example",
    "entrenamiento/data.yaml",
    "entrenamiento/dataset_report.json",
    "entrenamiento/model_baseline.json",
    "entrenamiento/splits/train.txt",
    "entrenamiento/splits/val.txt",
    "entrenamiento/splits/test.txt",
    "app/servidor.py",
    "app/static/index.html",
    "sql/migrations/001_schema_base.sql",
    "sql/migrations/002_upgrade_tracking_indexes.sql",
    "tools/auditar_dataset.py",
    "tools/crear_splits_agrupados.py",
    "tools/entrenar_modelo.py",
    "tools/evaluar_modelo.py",
    "tools/configurar_zonas.py",
    "tools/escaner_camara.py",
    "tools/recolector_fotos.py",
    "docs/ARQUITECTURA.md",
    "docs/CONFIGURACION_Y_OPERACION.md",
    "docs/ENTRENAMIENTO_Y_EVALUACION.md",
    "docs/SEGURIDAD.md",
)

DEPENDENCIAS = {
    "av": "av",
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "fastapi": "fastapi",
    "lap": "lap",
    "numpy": "numpy",
    "openai": "openai",
    "PIL": "pillow",
    "pyodbc": "pyodbc",
    "supervision": "supervision",
    "ultralytics": "ultralytics",
    "uvicorn": "uvicorn",
}


def fuentes_python() -> list[Path]:
    rutas = [RAIZ / "main.py"]
    for carpeta in ("app", "modulos", "tools"):
        rutas.extend(sorted((RAIZ / carpeta).rglob("*.py")))
    return rutas


def verificar_sintaxis() -> list[str]:
    errores = []
    for ruta in fuentes_python():
        relativa = ruta.relative_to(RAIZ)
        try:
            fuente = ruta.read_text(encoding="utf-8")
            compile(fuente, str(relativa), "exec")
        except (OSError, UnicodeError, SyntaxError) as error:
            errores.append(f"{relativa}: {error}")
    return errores


def verificar_archivos() -> list[str]:
    return [ruta for ruta in ARCHIVOS_ESENCIALES if not (RAIZ / ruta).exists()]


def verificar_dependencias() -> list[str]:
    faltantes = []
    for modulo, paquete in DEPENDENCIAS.items():
        if importlib.util.find_spec(modulo) is None:
            faltantes.append(paquete)
    return faltantes


def verificar_modelo() -> list[str]:
    """Valida contenedor, huella y metadatos mínimos sin deserializar PyTorch."""
    errores = []
    ruta_modelo = RAIZ / "best.pt"
    ruta_baseline = RAIZ / "entrenamiento" / "model_baseline.json"
    if not ruta_modelo.is_file() or not ruta_baseline.is_file():
        return ["Falta best.pt o entrenamiento/model_baseline.json."]

    try:
        baseline = json.loads(ruta_baseline.read_text(encoding="utf-8"))
        huella = hashlib.sha256(ruta_modelo.read_bytes()).hexdigest()
        esperada = baseline["checkpoint"]["sha256"]
        if huella != esperada:
            errores.append(f"SHA-256 inesperado: {huella}")

        if not zipfile.is_zipfile(ruta_modelo):
            errores.append("best.pt no es un contenedor PyTorch ZIP válido.")
            return errores
        with zipfile.ZipFile(ruta_modelo) as archivo:
            nombres = archivo.namelist()
            pickle = next((nombre for nombre in nombres if nombre.endswith("/data.pkl")), None)
            if pickle is None:
                errores.append("best.pt no contiene data.pkl.")
            else:
                metadatos = archivo.read(pickle)
                for texto in (b"detect", b"bebedero", b"comedero", b"ninfa"):
                    if texto not in metadatos:
                        errores.append(f"best.pt no declara {texto.decode()}.")
            archivo_danado = archivo.testzip()
            if archivo_danado:
                errores.append(f"Archivo interno corrupto en best.pt: {archivo_danado}")
    except (KeyError, OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        errores.append(str(error))
    return errores


def mostrar_lista(titulo: str, elementos: list[str]) -> None:
    estado = "ERROR" if elementos else "OK"
    print(f"[{estado}] {titulo}")
    for elemento in elementos:
        print(f"  - {elemento}")


def main() -> int:
    errores_sintaxis = verificar_sintaxis()
    archivos_faltantes = verificar_archivos()
    dependencias_faltantes = verificar_dependencias()
    errores_modelo = verificar_modelo()

    print(f"Python: {sys.version.split()[0]}")
    mostrar_lista("Sintaxis Python", errores_sintaxis)
    mostrar_lista("Archivos esenciales", archivos_faltantes)
    mostrar_lista("Integridad estática de best.pt", errores_modelo)
    mostrar_lista("Dependencias instaladas", dependencias_faltantes)

    return int(
        bool(
            errores_sintaxis
            or archivos_faltantes
            or errores_modelo
            or dependencias_faltantes
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
