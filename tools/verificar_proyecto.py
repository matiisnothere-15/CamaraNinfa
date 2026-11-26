"""Verificación liviana del proyecto sin abrir cámara ni conectar servicios.

Uso:
    python tools/verificar_proyecto.py

El comando comprueba sintaxis, archivos esenciales y disponibilidad de las
dependencias directas. Devuelve código 1 si encuentra un bloqueo.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ARCHIVOS_ESENCIALES = (
    "main.py",
    ".env.example",
    "modulos/detector_rfdetr.py",
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
    dependencias = dict(DEPENDENCIAS)
    for modulo, paquete in dependencias.items():
        if importlib.util.find_spec(modulo) is None:
            faltantes.append(paquete)
    if os.getenv("RFDETR_WEIGHTS_PATH", "").strip():
        if importlib.util.find_spec("rfdetr") is None:
            faltantes.append("rfdetr")
    else:
        tiene_inference = (
            importlib.util.find_spec("inference") is not None
            or importlib.util.find_spec("inference_models") is not None
        )
        if not tiene_inference:
            faltantes.append("inference")
    return faltantes


def verificar_gui() -> list[str]:
    """Detecta la variante headless de OpenCV sin abrir una ventana ni la cámara."""
    if os.getenv("NINFAS_HEADLESS", "0").strip().lower() in {"1", "true", "yes", "si"}:
        return []
    try:
        import cv2
    except ImportError:
        return []  # Se informa como dependencia faltante.
    for linea in cv2.getBuildInformation().splitlines():
        if "GUI:" in linea and "NONE" in linea.upper():
            return [
                "OpenCV no tiene ventanas. Ejecuta: python -m pip install "
                "--force-reinstall --no-deps opencv-contrib-python==4.11.0.86 "
                "(o usa NINFAS_HEADLESS=1)."
            ]
    return []


def verificar_modelo() -> list[str]:
    """Valida la configuración local del detector RF-DETR sin descargar modelos."""
    pesos = os.getenv("RFDETR_WEIGHTS_PATH", "").strip()
    if pesos:
        ruta = Path(pesos).expanduser()
        if not ruta.is_absolute():
            ruta = RAIZ / ruta
        if not ruta.is_file():
            return [f"No se encontraron los pesos RF-DETR: {ruta}"]
    return []


def verificar_contrato_rfdetr() -> list[str]:
    """Valida estáticamente el contrato del adaptador RF-DETR v6 sin cargar pesos."""
    errores = []
    ruta_detector = RAIZ / "modulos" / "detector_rfdetr.py"
    if not ruta_detector.is_file():
        return ["Falta modulos/detector_rfdetr.py."]

    try:
        fuente = ruta_detector.read_text(encoding="utf-8")
        ast.parse(fuente, filename=str(ruta_detector))
        for requerido in (
            "monitorninfas20/monitorninfas-6-rfdetr-nas-base-t1--c661c3",
            "bebedero",
            "comedero",
            "mushu",
            "shiro",
            "yukki",
        ):
            if requerido not in fuente:
                errores.append(
                    f"modulos/detector_rfdetr.py no declara '{requerido}'."
                )
    except (OSError, UnicodeError, SyntaxError) as error:
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
    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integracion",
        action="store_true",
        help="Verifica driver ODBC, migraciones SQL, credenciales en .env y fuente de video.",
    )
    parser.add_argument(
        "--probar-conexiones",
        action="store_true",
        help="Abre cámara y conecta Azure SQL/aplica migraciones; requiere --integracion.",
    )
    args = parser.parse_args(argv)
    if args.probar_conexiones and not args.integracion:
        parser.error("--probar-conexiones requiere --integracion")

    errores_sintaxis = verificar_sintaxis()
    archivos_faltantes = verificar_archivos()
    dependencias_faltantes = verificar_dependencias()
    errores_modelo = verificar_modelo()
    errores_gui = verificar_gui()

    print(f"Python: {sys.version.split()[0]}")
    mostrar_lista("Sintaxis Python", errores_sintaxis)
    mostrar_lista("Archivos esenciales", archivos_faltantes)
    mostrar_lista("Configuración del detector activo (sin cargar pesos)", errores_modelo)
    mostrar_lista("Dependencias instaladas", dependencias_faltantes)
    mostrar_lista("OpenCV para el modo de ejecución", errores_gui)
    if not os.getenv("RFDETR_WEIGHTS_PATH", "").strip():
        if not os.getenv("ROBOFLOW_API_KEY", "").strip():
            print("[PENDIENTE] ROBOFLOW_API_KEY no configurada; acceso/caché del modelo sin validar.")
        print("[INFO] Esta revisión no carga RF-DETR ni mide latencia/FPS en la cámara.")

    errores_integracion: list[str] = []
    if args.integracion:
        diagnostico = verificar_integracion_entorno(probar_conexiones=args.probar_conexiones)
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
            or errores_gui
            or errores_integracion
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
