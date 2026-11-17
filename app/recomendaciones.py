"""Reexportación del motor unificado de recomendaciones para el servidor web."""

from modulos.recomendaciones import (
    ACTIVIDAD_LETARGO,
    FRACCION_ESTRES_DIA,
    HORAS_SIN_BEBER_ATENCION,
    HORAS_SIN_BEBER_URGENTE,
    HORAS_SIN_COMER_ATENCION,
    HORAS_SIN_COMER_URGENTE,
    MINUTOS_MONITOR_APAGADO,
    generar,
    generar_recomendaciones,
)

__all__ = [
    "ACTIVIDAD_LETARGO",
    "FRACCION_ESTRES_DIA",
    "HORAS_SIN_BEBER_ATENCION",
    "HORAS_SIN_BEBER_URGENTE",
    "HORAS_SIN_COMER_ATENCION",
    "HORAS_SIN_COMER_URGENTE",
    "MINUTOS_MONITOR_APAGADO",
    "generar",
    "generar_recomendaciones",
]
