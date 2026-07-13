"""Normalización de métricas de Ultralytics a un contrato JSON estable."""

from __future__ import annotations


def _lista(valor) -> list:
    if valor is None:
        return []
    if hasattr(valor, "tolist"):
        valor = valor.tolist()
    if isinstance(valor, (int, float)):
        return [valor]
    return list(valor)


def _numero(valor, posicion: int) -> float | None:
    valores = _lista(valor)
    if posicion >= len(valores):
        return None
    return float(valores[posicion])


def extraer_metricas_deteccion(box, nombres) -> dict:
    """Extrae precisión, recall y AP global y por clase de ``DetMetrics.box``."""
    if isinstance(nombres, list):
        nombres = dict(enumerate(nombres))
    nombres = {int(indice): str(nombre) for indice, nombre in nombres.items()}
    indices = [int(indice) for indice in _lista(getattr(box, "ap_class_index", None))]
    if not indices:
        indices = sorted(nombres)

    por_clase = {}
    for posicion, indice in enumerate(indices):
        por_clase[nombres.get(indice, str(indice))] = {
            "precision": _numero(getattr(box, "p", None), posicion),
            "recall": _numero(getattr(box, "r", None), posicion),
            "f1": _numero(getattr(box, "f1", None), posicion),
            "map50": _numero(getattr(box, "ap50", None), posicion),
            "map50_95": _numero(getattr(box, "ap", None), posicion),
        }

    return {
        "global": {
            "precision": float(box.mp),
            "recall": float(box.mr),
            "map50": float(box.map50),
            "map75": float(box.map75),
            "map50_95": float(box.map),
        },
        "por_clase": por_clase,
    }
