# Validación final del proyecto — 12 de julio de 2026

> Nota de revisión del 17 de noviembre de 2026: este documento es histórico.
> El JSON `best_test_2026-07-12.json` fue sustituido por una evaluación del
> 16 de noviembre para el checkpoint `668e1879…0a7e`; ya no respalda las métricas
> ni el checkpoint de las tablas siguientes. Tampoco valida el nuevo RF-DETR NAS.

## Resultado

El proyecto supera la validación local de código, contratos, dependencias,
dataset, checkpoint, API y frontend. El checkpoint `best.pt` también pudo
cargarse y evaluarse realmente en CPU con Ultralytics; no fue reemplazado ni
modificado.

| Comprobación | Resultado |
|---|---|
| Dependencias fijadas | `pip check`: sin conflictos |
| Verificador del proyecto | Sintaxis, archivos, checkpoint y dependencias: OK |
| Pruebas | 91 aprobadas |
| Ruff | Sin observaciones |
| JavaScript del panel | 1 bloque embebido con sintaxis válida |
| Smoke test | Imports, FastAPI, CSP y Supervision: OK |
| Auditoría del dataset | OK, sin fugas detectadas |
| Evaluación YOLO | 20 imágenes y 76 objetos procesados correctamente |

El entorno de esta ejecución utilizó Python 3.12.13, Ultralytics 8.4.92,
Supervision 0.29.1 y PyTorch 2.13.0 CPU. El objetivo documentado del proyecto
continúa siendo Python 3.11.

## Dataset evaluado

- 178 imágenes y 605 objetos en total.
- Train: 137 imágenes y 446 objetos.
- Validación: 21 imágenes y 83 objetos.
- Test: 20 imágenes y 76 objetos, incluidas 6 imágenes negativas.
- 138 fuentes agrupadas sin repetición entre splits.
- Sin duplicados exactos ni pares dHash ≤ 2 compartidos entre splits.
- Huella del dataset:
  `c2b80049f0a1d8c92d171f4f6d04e7315424d63f2e779048d8d43cbf7d42c474`.

La auditoría mantiene dos advertencias: el dataset completo es pequeño y el
test tiene menos de 50 imágenes. Por ello las métricas tienen alta varianza.

## Evaluación del checkpoint actual

Checkpoint:
`4cf23872a67b444a02ece450d5af6cb18846ffa5e32c3006ed41d8380000e05b`.

| Clase | Precisión | Recall | F1 | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| Bebedero | 0.636 | 0.941 | 0.759 | 0.758 | 0.604 |
| Comedero | 0.596 | 0.591 | 0.593 | 0.510 | 0.401 |
| Ninfa | 0.709 | 0.794 | 0.749 | 0.828 | 0.630 |
| Global | 0.647 | 0.775 | — | 0.699 | 0.545 |

El mAP75 global fue `0.631`. La inferencia reportada en este equipo fue de
`43.2 ms` por imagen, sin incluir captura de cámara ni dibujo del panel.

`ninfa` es la clase más sólida. `comedero` es el principal punto débil y debe
recibir prioridad al recolectar y revisar nuevas anotaciones: cambios de luz,
oclusiones, recipientes vacíos y fondos visualmente parecidos.

El informe completo y trazable está en
[`best_test_2026-07-12.json`](../entrenamiento/evaluaciones/best_test_2026-07-12.json).
Las métricas históricas embebidas en el checkpoint no se comparan directamente
con estas porque procedían del split anterior contaminado.

## Comandos reproducibles

```powershell
python tools/auditar_dataset.py
python tools/verificar_proyecto.py
pytest
ruff check main.py app modulos tools tests
python tools/evaluar_modelo.py `
  --modelo best.pt `
  --split test `
  --device cpu `
  --workers 0 `
  --salida entrenamiento/evaluaciones/best_test_2026-07-12.json
```

## Validaciones que requieren el entorno real

La revisión local no sustituye las siguientes pruebas de aceptación:

- transmisión prolongada con la webcam o RTSP reales y reconexiones;
- calidad de tracking e identidad con ambas aves, de día y en infrarrojo;
- escritura y recuperación contra la instancia real de Azure SQL;
- conversación completa contra el deployment real de Microsoft Foundry;
- revisión veterinaria de umbrales, alertas y textos de recomendación.

Antes de presentar el sistema como listo para producción conviene ejecutar una
sesión continua de varias horas, revisar manualmente sus eventos y ampliar el
holdout con otros días, iluminaciones y posiciones de cámara.
