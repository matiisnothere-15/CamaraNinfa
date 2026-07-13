"""Aplica las migraciones pendientes a Azure SQL.

Uso desde la raíz del proyecto:
    python tools/migrar_bd.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv

from modulos.base_datos import ErrorBaseDatos, aplicar_migraciones


def main() -> int:
    load_dotenv(RAIZ / ".env")
    try:
        aplicadas = aplicar_migraciones(RAIZ / "sql" / "migrations")
    except ErrorBaseDatos as error:
        print(f"No se pudieron aplicar las migraciones: {error}")
        return 1

    if aplicadas:
        print("Migraciones aplicadas:")
        for nombre in aplicadas:
            print(f"- {nombre}")
    else:
        print("La base de datos ya está actualizada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
