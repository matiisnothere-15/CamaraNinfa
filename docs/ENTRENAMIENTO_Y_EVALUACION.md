# Entrenamiento y evaluación

## Objetivo

El modelo de producción es un detector YOLOv8 con tres clases:

| ID | Clase |
|---:|---|
| 0 | `bebedero` |
| 1 | `comedero` |
| 2 | `ninfa` |

Las etiquetas se almacenan como polígonos YOLO normalizados. Al entrenar una
tarea `detect`, Ultralytics utiliza la caja envolvente de cada segmento. Esto
preserva una fuente de anotación uniforme y permite seguir usando un detector
compatible con el pipeline actual.

## Estado del dataset

El export físico de Roboflow contiene 198 imágenes y 679 objetos. El split
lógico definido por manifiestos utiliza 178 imágenes:

| Split | Fuentes | Imágenes | Objetos |
|---|---:|---:|---:|
| Train | 97 | 137 | 446 |
| Validación | 21 | 21 | 83 |
| Test | 20 | 20 | 76 |

La diferencia se debe a que train puede conservar variantes aumentadas de una
misma fuente, mientras validación y test usan una sola variante. Veinte
variantes que habrían sobreponderado fuentes de evaluación quedan fuera de los
manifiestos, pero no se borran del export físico.

Todas las clases aparecen en los tres splits. El informe reproducible está en
`entrenamiento/dataset_report.json`.

## Correcciones aplicadas

- Rutas de `data.yaml` cambiadas a manifiestos portables.
- Ocho cajas válidas convertidas a polígonos rectangulares equivalentes.
- Una anotación duplicada de comedero de aproximadamente 1 × 1,5 píxeles
  eliminada tras revisión visual.
- Fuentes agrupadas con semilla 42 y dHash de 256 bits, umbral Hamming 2.
- Variantes de una misma fuente asignadas siempre al mismo split.
- Cero duplicados exactos, IDs fuente compartidos o pares dHash ≤ 2 detectados
  entre los manifiestos actuales.

El agrupamiento perceptual reduce fuga evidente; no demuestra independencia
semántica. Las imágenes siguen procediendo de una misma cámara y jornada.

## Auditoría

```powershell
python tools/auditar_dataset.py
```

Para guardar un informe:

```powershell
python tools/auditar_dataset.py `
  --salida entrenamiento/dataset_report.json
```

La auditoría comprueba:

- rutas y manifiestos;
- lectura de imágenes y dimensiones;
- correspondencia imagen/etiqueta;
- clases, coordenadas, polígonos degenerados y duplicados;
- mezcla de cajas y polígonos dentro de un archivo;
- balance e imágenes negativas;
- archivos, fuentes y similitud visual entre splits;
- huella SHA-256 de configuración, manifiestos, imágenes y etiquetas.

Un informe `ok: true` puede contener advertencias. Actualmente advierte que el
dataset y el test son pequeños.

## Regeneración de splits

Solo regenera los manifiestos si cambió el dataset o la política de split:

```powershell
python tools/crear_splits_agrupados.py --force
python tools/auditar_dataset.py `
  --salida entrenamiento/dataset_report.json
```

El generador necesita las imágenes fuente de `dataset/images`. Forma
componentes si alguna variante exportada tiene dHash a distancia ≤ 2 de otra
fuente. Componentes grandes se reservan para train; los demás se distribuyen
aproximadamente 70/15/15. Para evaluación selecciona la variante más cercana a
la fuente original.

Cambiar `--seed` o `--umbral-similitud` crea otro benchmark. No compares
métricas entre manifiestos con distinta huella como si fueran el mismo test.

## Entrenamiento reproducible

```powershell
python tools/entrenar_modelo.py
```

Valores predeterminados:

| Parámetro | Valor |
|---|---:|
| Checkpoint inicial | `yolov8n.pt` |
| Épocas máximas | 100 |
| Imagen | 512 |
| Batch | 16 |
| Early stopping | 25 épocas |
| Seed | 42 |
| Determinista | Sí |
| Workers en Windows | 0 |
| Cierre de mosaic | Últimas 10 épocas |

Ejemplo con GPU y caché en disco:

```powershell
python tools/entrenar_modelo.py `
  --device 0 `
  --batch 16 `
  --cache disk `
  --name experimento_gpu_01
```

El script ejecuta primero la auditoría, exige un checkpoint de detección y
guarda resultados bajo `runs/entrenamiento/`. Ultralytics conserva además sus
argumentos, curvas, matrices y checkpoints.

Una semilla y modo determinista mejoran reproducibilidad, pero versiones de
CUDA, drivers y hardware distintos todavía pueden producir pequeñas
variaciones.

## Evaluación

Usa validación durante desarrollo. Usa test solo para una decisión final:

```powershell
python tools/evaluar_modelo.py `
  --modelo runs/entrenamiento/experimento_gpu_01/weights/best.pt `
  --split test
```

El JSON resultante contiene:

- SHA-256 del modelo y dataset;
- versiones de Python y Ultralytics;
- split y configuración;
- velocidad de preproceso, inferencia, pérdida y postproceso;
- métricas globales y por clase.

### Interpretación de métricas

- **Precision**: fracción de detecciones informadas que son correctas. Una
  precisión baja genera falsas aves o platos.
- **Recall**: fracción de objetos reales que el modelo encuentra. En este
  proyecto es crítico no perder ninfas, comederos o bebederos.
- **F1**: balance armónico entre precision y recall.
- **mAP50**: average precision a IoU 0,50.
- **mAP75**: criterio de localización más estricto a IoU 0,75.
- **mAP50-95**: promedio de AP entre IoU 0,50 y 0,95; debe ser la métrica
  principal al comparar detectores.

No uses una sola métrica global. Revisa cada clase, falsos positivos en frames
negativos, matriz de confusión y desempeño temporal sobre video.

## Baseline histórico

`best.pt` contiene métricas embebidas del entrenamiento anterior:

| Métrica | Valor |
|---|---:|
| Precision | 0,70728 |
| Recall | 0,83679 |
| mAP50 | 0,74622 |
| mAP50-95 | 0,61753 |

Ese modelo se entrenó durante 50 épocas a 640 px con Ultralytics 8.3.250. Las
métricas pertenecen al split anterior, que contenía fotogramas temporalmente
casi idénticos entre train y validación. Por eso están etiquetadas como
`historico_no_comparable` en `entrenamiento/model_baseline.json`.

## Promoción de un modelo

Antes de reemplazar `best.pt`:

1. Conserva el JSON de evaluación y la huella del dataset.
2. Compara métricas por clase contra un checkpoint reevaluado sobre el mismo
   test, no contra el baseline histórico.
3. Revisa visualmente errores de val y test.
4. Prueba video continuo diurno e infrarrojo.
5. Evalúa IDs y eventos, no solo cajas: cambios de track pueden afectar la FSM.
6. Mide latencia en el equipo de producción.
7. Copia el checkpoint anterior antes de promover el nuevo.
8. Ejecuta todas las pruebas y una sesión controlada del monitor.

## Próxima recolección recomendada

- Separar por sesión o día antes de aplicar aumentos.
- Reservar un holdout de otro día que nunca entre en train ni val.
- Incluir luz diurna, infrarrojo, oclusiones, jaula vacía y personas cerca.
- Capturar comederos y bebederos vacíos, desplazados o parcialmente tapados.
- Mantener frames negativos para medir falsas alarmas.
- No exportar aumentos a validación o test.

Referencias oficiales:

- [Formato de segmentación YOLO](https://docs.ultralytics.com/datasets/segment/)
- [Entrenamiento Ultralytics](https://docs.ultralytics.com/modes/train/)
- [Validación y métricas](https://docs.ultralytics.com/modes/val/)
