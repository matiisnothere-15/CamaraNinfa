"""Verificación liviana del proyecto sin abrir cámara ni conectar servicios.

Uso:
    python tools/verificar_proyecto.py

El comando comprueba sintaxis, archivos esenciales y disponibilidad de las
dependencias directas. Devuelve código 1 si encuentra un bloqueo.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ARCHIVOS_ESENCIALES = (
    "main.py",
    "best.pt",
    "requirements.txt",
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


def verificar_integracion_entorno(
    probar_conexiones: bool = False,
) -> dict[str, list[str]]:
    """Diagnostica driver ODBC, migraciones SQL, fuente de video y credenciales en .env."""
    errores: list[str] = []
    pendientes: list[str] = []
    ok: list[str] = []

    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
    except Exception:
        pass

    from modulos.base_datos import (
        ErrorBaseDatos,
        _cargar_config_azure,
        aplicar_migraciones,
        dividir_batches_sql,
    )
    from modulos.fuente_video import (
        abrir_fuente_video,
        describir_fuente,
        es_rtsp,
        resolver_fuente,
    )

    driver_config = os.getenv("AZURE_DRIVER", "{ODBC Driver 18 for SQL Server}")
    driver_nombre = driver_config.strip("{} ").strip()
    try:
        import pyodbc

        drivers = pyodbc.drivers()
        if driver_nombre in drivers:
            ok.append(f"Driver ODBC disponible: {driver_nombre}")
        else:
            errores.append(
                f"Falta el driver ODBC '{driver_nombre}'. Disponibles: {', '.join(drivers) or 'ninguno'}"
            )
    except Exception as error:
        errores.append(f"No se pudo inspeccionar pyodbc: {error}")

    archivos_sql = sorted((RAIZ / "sql" / "migrations").glob("*.sql"))
    if not archivos_sql:
        errores.append("No se encontraron archivos *.sql en sql/migrations.")
    else:
        total_batches = 0
        for archivo in archivos_sql:
            batches = dividir_batches_sql(archivo.read_text(encoding="utf-8"))
            if not batches:
                errores.append(f"Migración vacía o inválida: {archivo.name}")
            total_batches += len(batches)
        if total_batches > 0:
            ok.append(
                f"Migraciones SQL válidas: {len(archivos_sql)} archivos ({total_batches} batches)."
            )

    config_azure = _cargar_config_azure()
    if all(
        config_azure.get(clave)
        for clave in ("server", "database", "username", "password")
    ):
        ok.append("Credenciales de Azure SQL configuradas en .env.")
        if probar_conexiones:
            try:
                aplicadas = aplicar_migraciones(RAIZ / "sql" / "migrations")
                ok.append(
                    f"Azure SQL accesible (migraciones nuevas: {len(aplicadas)})."
                )
            except ErrorBaseDatos as error:
                errores.append(f"Fallo de conexión/migración Azure SQL: {error}")
    else:
        pendientes.append(
            "Azure SQL sin credenciales en .env (AZURE_SERVER/DATABASE/USERNAME/PASSWORD)."
        )

    if all(
        os.getenv(clave)
        for clave in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_API_KEY", "FOUNDRY_MODEL")
    ):
        ok.append("Credenciales de Microsoft Foundry configuradas en .env.")
    else:
        pendientes.append(
            "Microsoft Foundry sin credenciales en .env (FOUNDRY_PROJECT_ENDPOINT/API_KEY/MODEL)."
        )

    try:
        fuente = resolver_fuente()
        desc = describir_fuente(fuente)
        if es_rtsp(fuente):
            ok.append(f"Fuente RTSP configurada: {desc}")
        else:
            pendientes.append(
                f"Cámara Tapo/RTSP sin credenciales en .env; fuente actual: {desc}"
            )
        if probar_conexiones:
            captura = abrir_fuente_video(fuente)
            try:
                leido, frame = captura.read() if captura.isOpened() else (False, None)
                if captura.isOpened() and leido and frame is not None:
                    ok.append(f"Captura de prueba exitosa desde {desc}.")
                else:
                    pendientes.append(
                        f"Fuente {desc} sin señal activa durante la prueba."
                    )
            finally:
                captura.release()
    except Exception as error:
        pendientes.append(f"No se pudo resolver/abrir la fuente de video: {error}")

    return {"ok": ok, "errores": errores, "pendientes": pendientes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integracion",
        action="store_true",
        help="Verifica driver ODBC, migraciones SQL, credenciales en .env y fuente de video.",
    )
    args = parser.parse_args(argv)

    errores_sintaxis = verificar_sintaxis()
    archivos_faltantes = verificar_archivos()
    dependencias_faltantes = verificar_dependencias()
    errores_modelo = verificar_modelo()

    print(f"Python: {sys.version.split()[0]}")
    mostrar_lista("Sintaxis Python", errores_sintaxis)
    mostrar_lista("Archivos esenciales", archivos_faltantes)
    mostrar_lista("Integridad estática de best.pt", errores_modelo)
    mostrar_lista("Dependencias instaladas", dependencias_faltantes)

    errores_integracion: list[str] = []
    if args.integracion:
        diagnostico = verificar_integracion_entorno(probar_conexiones=True)
        for item in diagnostico["ok"]:
            print(f"[OK] {item}")
        for item in diagnostico["pendientes"]:
            print(f"[PENDIENTE] {item}")
        errores_integracion = diagnostico["errores"]
        if errores_integracion:
            mostrar_lista("Errores de integración", errores_integracion)

    return int(
        bool(
            errores_sintaxis
            or archivos_faltantes
            or errores_modelo
            or dependencias_faltantes
            or errores_integracion
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
