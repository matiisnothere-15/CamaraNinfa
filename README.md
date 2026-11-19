# Monitor de Ninfas

Monitoreo local en tiempo real para ninfas domésticas mediante visión por
computador e IA. El sistema detecta `ninfa`, `comedero` y `bebedero` con
**RF-DETR** como detector predeterminado (`NINFAS_DETECTOR=rfdetr`, modelo
Roboflow `monitorninfas20/monitorninfas-5-rfdetr-nas-base-t1--96ff59` o pesos
locales `.pth`) y permite usar el modelo YOLOv8 propio (`best.pt`) mediante
selección explícita; conserva identidades de tracking con BoT-SORT, infiere
estados de comportamiento, analiza movimiento y audio, persiste eventos en Azure
SQL y los presenta en una API y un panel web. Un asistente opcional de Microsoft
Foundry responde preguntas usando herramientas de lectura controladas.

> Este proyecto es una ayuda de observación. Sus estados, alertas y
> recomendaciones son heurísticos y no constituyen diagnóstico veterinario.

## Funcionalidades implementadas

- Una sola captura de webcam, ventana de Windows o cámara RTSP/HTTP, con
  reconexión automática.
- Detección predeterminada con **RF-DETR** (vía `inference` / `inference-gpu` o
  `rfdetr` con pesos `.pth`) y soporte opcional explícito para YOLOv8 (`best.pt`),
  integrados con tracking persistente BoT-SORT de Ultralytics.
- Conversión a `supervision.Detections`, filtrado, cajas, etiquetas, trazas y
  `PolygonZone` con [Supervision](https://supervision.roboflow.com/latest/).
- Zonas fijas normalizadas o zonas dinámicas alrededor de platos detectados.
- Máquina de estados independiente por track: `ACTIVO`, `INACTIVO`,
  `COMIENDO`, `BEBIENDO` y `DESCONOCIDO`.
- Identificación exclusiva por color para dos tipos distinguibles de plumaje;
  en visión infrarroja se conserva la incertidumbre y no se inventa un nombre.
- Actividad normalizada como porcentaje de la diagonal del frame por minuto.
- Audio RTSP clasificado como silencio, sonidos, grito o ruido fuerte.
- Alertas por cuatro horas sin alimentación o hidratación observada.
- Persistencia asíncrona y transaccional en Azure SQL mediante una cola FIFO.
- API FastAPI, panel web, estadísticas por ave y recomendaciones por reglas.
- Asistente opcional con Microsoft Foundry Responses API y herramientas
  cerradas de solo lectura.
- Dataset auditable, splits agrupados, entrenamiento reproducible y evaluación
  con métricas globales y por clase.

## Arquitectura

```mermaid
flowchart LR
    C["Webcam, Ventana o Tapo RTSP"] --> Y["RF-DETR (predeterminado) o YOLOv8 + BoT-SORT"]
    Y --> S["Supervision: detecciones, zonas y anotación"]
    S --> I["Identidad por color"]
    S --> F["Máquina de estados por track"]
    I --> F
    A["Audio RTSP"] --> E["Estado global y recomendaciones"]
    F --> E
    F --> Q["Cola única de persistencia"]
    E --> Q
    Q --> DB["Azure SQL"]
    DB --> API["FastAPI"]
    API --> W["Panel web"]
    API --> AI["Asistente Microsoft Foundry"]
```

BoT-SORT pertenece a Ultralytics y [modulos/detector_rfdetr.py](modulos/detector_rfdetr.py)
adapta la salida de RF-DETR a la misma interfaz `track()`/`predict()`. Supervision
se utiliza como capa común de postprocesamiento, zonas y visualización; no hay un
segundo tracker compitiendo por los IDs.

La explicación detallada está en [Arquitectura](docs/ARQUITECTURA.md).

## Requisitos

- Python 3.11.
- Webcam, ventana de Windows o cámara con una transmisión RTSP/HTTP compatible con OpenCV.
- Para el detector predeterminado (**RF-DETR**):
  - Con modelo Roboflow (`ROBOFLOW_MODEL_ID=monitorninfas20/monitorninfas-5-rfdetr-nas-base-t1--96ff59`):
    instala el backend opcional `inference-gpu` (con GPU CUDA) o `inference` (CPU)
    y define `ROBOFLOW_API_KEY` en `.env` para descargar y cachear el modelo la primera vez.
  - Con pesos `.pth` locales (`RFDETR_WEIGHTS_PATH`): instala el paquete opcional `rfdetr`.
- Para el respaldo YOLOv8 (`NINFAS_DETECTOR=yolo`): `best.pt` en la raíz del proyecto.
- Azure SQL y [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
  solamente si se requiere persistencia y panel con datos.
- Una GPU compatible es recomendable para entrenar o acelerar inferencia, pero no
  es obligatoria para ejecutar el monitor o evaluar en CPU.

## Instalación

En PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Instala además el backend opcional del detector RF-DETR según tu modo de uso.
Para el modelo alojado en Roboflow (con GPU CUDA o solo CPU):

```powershell
pip install inference-gpu
```

En equipos sin GPU CUDA puedes usar `pip install inference`. Para usar pesos
`.pth` locales configurando `RFDETR_WEIGHTS_PATH` en `.env`:

```powershell
pip install rfdetr
```

Para desarrollo:

```powershell
pip install -r requirements-dev.txt
```

En Linux o macOS cambia la activación por `source .venv/bin/activate` y copia
el entorno con `cp .env.example .env`. Si necesitas volver al detector YOLOv8
histórico sin instalar `inference` ni `rfdetr`, define `NINFAS_DETECTOR=yolo` en `.env`.

## Configuración mínima de cámara

Si no se configuran variables Tapo, el monitor utiliza la webcam indicada por
`CAMARA_PC_INDICE`.

```env
CAMARA_PC_INDICE=0
```

Para cualquier cámara con URL de video completa (tiene prioridad):

```env
CAMARA_RTSP_URL=rtsp://usuario:clave@192.168.1.100:554/ruta
```

Para una Tapo con RTSP:

```env
TAPO_USER=usuario_camara
TAPO_PASS=contrasena_camara
TAPO_IP=192.168.1.100
```

El monitor construye `rtsp://usuario:clave@IP:554/stream2`; usuario y clave se
codifican antes de incorporarse a la URL. El audio se analiza únicamente en el
modo RTSP. Con webcam se muestra `Sin audio`.

## Ejecución

### Monitor de video

```powershell
python main.py
```

Presiona `q` en la ventana de OpenCV para cerrar. Si Azure no está configurado,
el monitor funciona en modo local, pero no conserva historial al terminar.

### Azure SQL y panel web

Completa las variables `AZURE_*` de `.env`, instala ODBC Driver 18 y aplica las
migraciones idempotentes:

```powershell
python tools/migrar_bd.py
uvicorn app.servidor:app --host 127.0.0.1 --port 8123
```

Abre <http://127.0.0.1:8123>. La API y el panel necesitan Azure SQL para
consultar datos; si la base no está disponible responden con un error 503 sin
exponer detalles internos.

Antes de migrar una base existente, realiza una copia de seguridad. Las
migraciones viven en `sql/migrations/` y se registran en `SchemaMigrations`.

Consulta [Configuración y operación](docs/CONFIGURACION_Y_OPERACION.md) para
los modos de despliegue, zonas y solución de problemas.

## Zonas y comportamiento

Las zonas fijas se expresan con puntos normalizados entre 0 y 1:

```env
ZONA_COMEDERO=0.10,0.65;0.35,0.65;0.35,0.95;0.10,0.95
ZONA_BEBEDERO=0.55,0.65;0.80,0.65;0.80,0.95;0.55,0.95
```

Si se omiten, se crean zonas dinámicas con un margen alrededor de los platos
detectados. El centro de la caja del ave activa la zona. Si comedero y bebedero
se superponen para la misma detección, el estado queda como `DESCONOCIDO`.

Para reducir falsos eventos, cada transición exige permanencia:

| Estado candidato | Confirmación |
|---|---:|
| Activo | 1 s |
| Comiendo | 2 s |
| Bebiendo | 2 s |
| Inactivo | 10 s |

Una pérdida de tracking de hasta tres segundos no cierra el evento. Estos
valores se encuentran en `ConfiguracionComportamiento`.

## Datos persistidos

`Aves` conserva nombre, descripción de color y notas. `BitacoraAves` registra:

| Categoría | Contenido |
|---|---|
| `Accion` | Inicio y fin de alimentación o hidratación, ave y track |
| `Comportamiento` | Inicio y fin de movimiento o inactividad |
| `Estado` | Cambios del estado global estabilizado |
| `Salud` | Activación de alertas sin comer o beber |
| `Snapshot` | Ánimo, actividad, audio y horas sin comer/beber cada 5 minutos |
| `Recomendacion` | Consejos generados en cada snapshot |

Al reiniciar, el monitor recupera la última alimentación e hidratación por ave
para no reiniciar artificialmente los contadores. Las escrituras se vacían al
cerrar el proceso.

## Asistente Microsoft Foundry

Configura un endpoint de proyecto y un modelo disponible en Microsoft Foundry:

```env
FOUNDRY_PROJECT_ENDPOINT=https://recurso.services.ai.azure.com/api/projects/proyecto
FOUNDRY_API_KEY=clave_foundry
FOUNDRY_MODEL=gpt-5-mini
NINFAS_AGENT_API_KEY=una_clave_de_al_menos_32_caracteres
```

El panel llama `/api/asistente` dentro de `app.servidor`; no necesita un segundo
servidor. Para utilizar el cliente de consola, inicia la API reducida:

```powershell
uvicorn app.servidor_agente:app --host 127.0.0.1 --port 8124
python -m app.agente_foundry "¿Cómo está Mushu en las últimas 24 horas?"
```

Las herramientas permitidas son `obtener_estado_ave` y
`obtener_recomendaciones_monitor`. Las credenciales permanecen en el backend.
Ánimo, audio y actividad son mediciones globales de la jaula, aunque la comida
y bebida sí pueden asociarse a un ave identificada.

Para exposición remota se requiere HTTPS, hosts explícitos y claves de al menos
32 caracteres. Revisa [Seguridad](docs/SEGURIDAD.md); no publiques Uvicorn
directamente en Internet.

## Dataset, entrenamiento y evaluación

El dataset lógico actual contiene 178 imágenes de 138 fuentes: 137 para train,
21 para validación y 20 para test. Todas las clases están representadas y la
auditoría no encuentra fuentes, archivos idénticos ni pares dHash ≤ 2
compartidos entre splits. El test sigue siendo pequeño y proviene de la misma
cámara/jornada, por lo que sus métricas tendrán alta varianza.

```powershell
python tools/auditar_dataset.py
python tools/entrenar_modelo.py
python tools/evaluar_modelo.py `
  --modelo runs/entrenamiento/yolov8n_ninfas_512_seed42/weights/best.pt `
  --split test
```

El evaluador genera precision, recall, F1, mAP50, mAP75 y mAP50-95 globales y
por clase, además de la huella del dataset y el checkpoint. No reemplaces
`best.pt` hasta evaluar el nuevo modelo en test y en video real.

El checkpoint actual conserva un baseline histórico en
`entrenamiento/model_baseline.json`. Sus métricas pertenecen al split anterior
con fuga temporal y están marcadas como no comparables.

La primera evaluación reproducible sobre el test agrupado está en
[`entrenamiento/evaluaciones/best_test_2026-07-12.json`](entrenamiento/evaluaciones/best_test_2026-07-12.json):
precisión `0.647`, recall `0.775`, mAP50 `0.699` y mAP50-95 `0.545`. El test
solo contiene 20 imágenes, por lo que estos valores son una línea base y no
una estimación definitiva de desempeño en producción.

Consulta [Entrenamiento y evaluación](docs/ENTRENAMIENTO_Y_EVALUACION.md).

## Pruebas y calidad

Sin abrir cámara ni contactar servicios externos:

```powershell
python -m unittest discover -s tests -v
python tools/verificar_proyecto.py
```

Con dependencias de desarrollo:

```powershell
pytest
ruff check main.py app modulos tools tests
```

`verificar_proyecto.py` también comprueba dependencias instaladas; retorna un
código distinto de cero si falta alguna.

## Seguridad

- `.env` y `config/credenciales.py` están excluidos de Git.
- Las consultas SQL usan parámetros y las migraciones están versionadas.
- Escrituras del panel y llamadas Foundry solo se permiten desde localhost si
  `NINFAS_ADMIN_API_KEY` no está configurada.
- En acceso remoto, la clave administrativa viaja únicamente sobre HTTPS y el
  panel la mantiene en memoria, nunca en `localStorage`.
- Hay validación estricta, límites de cuerpo, rate limiting, hosts confiables,
  CSP, escape de HTML y respuestas sin detalles internos.
- La documentación interactiva está desactivada salvo
  `NINFAS_ENABLE_DOCS=1`.

Estas medidas no sustituyen un proxy TLS, firewall, rotación de secretos,
observabilidad ni autenticación multiusuario en un despliegue público.

## Estructura principal

```text
main.py                         Orquestación del monitor
best.pt                         Detector YOLOv8 opcional (`NINFAS_DETECTOR=yolo`)
modulos/
  detector_rfdetr.py            Adaptador RF-DETR predeterminado + BoT-SORT
  camara.py                     Captura y reconexión
  vision_supervision.py         Detecciones, zonas y anotadores
  comportamiento.py             Máquina de estados por track
  identificador.py              Identidad exclusiva por color
  movement_analysis.py          Actividad normalizada
  audio_analysis.py             Audio RTSP
  health_monitor.py             Contadores y alertas por ave
  base_datos.py                 Repositorio y cola Azure SQL
app/
  servidor.py                   API y panel
  servidor_agente.py            API mínima para herramientas externas
  agente_foundry.py             Orquestación del asistente
  static/                       Interfaz web
sql/migrations/                 Esquema versionado de Azure SQL
entrenamiento/                  Dataset, manifiestos e informes
tools/                          Auditoría, migración, entrenamiento y evaluación
tests/                          Pruebas unitarias y contratos estructurales
archivo/                        Prototipos históricos no ejecutados
```

## Limitaciones conocidas

- Comer y beber se infiere por permanencia de la caja en una zona; no se
  detecta todavía el contacto del pico ni la ingesta efectiva.
- La identidad por color requiere dos plumajes configurados y distinguibles.
  No es reconocimiento biométrico y se desactiva sin información cromática.
- Los estados de ánimo y recomendaciones son reglas globales, no diagnósticos.
- El dataset es pequeño, de una jaula y una jornada; falta un holdout externo
  con otros días, iluminación, oclusiones y posiciones de cámara.
- El panel depende de Azure SQL; el monitor de video sí puede operar sin base.
- El código del proyecto está protegido bajo los términos de [`LICENSE`](LICENSE).
  El dataset exportado declara licencia CC BY 4.0.

## Documentación

- [Arquitectura](docs/ARQUITECTURA.md)
- [Configuración y operación](docs/CONFIGURACION_Y_OPERACION.md)
- [Entrenamiento y evaluación](docs/ENTRENAMIENTO_Y_EVALUACION.md)
- [Seguridad](docs/SEGURIDAD.md)
- [Validación final del proyecto](docs/VALIDACION_FINAL_2026-07-12.md)
- [Entrega técnica y trabajo pendiente](docs/ENTREGA_Y_PENDIENTES.md)
- [Línea base técnica original](docs/BASELINE_2026-07-12.md)
- [Configuración de Azure Boards y CI](docs/azure-boards/CONFIGURACION.md)

## Referencias técnicas

- [Ultralytics: tracking](https://docs.ultralytics.com/modes/track/)
- [Ultralytics: entrenamiento](https://docs.ultralytics.com/modes/train/)
- [Ultralytics: validación y métricas](https://docs.ultralytics.com/modes/val/)
- [Supervision: PolygonZone](https://supervision.roboflow.com/latest/detection/tools/polygon_zone/)
- [Microsoft Foundry Responses API](https://learn.microsoft.com/azure/foundry/agents/quickstarts/responses-api)
- [Microsoft ODBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
