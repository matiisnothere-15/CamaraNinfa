# Configuración y operación

## Preparación

1. Instala Python 3.11 y crea un entorno virtual.
2. Instala `requirements.txt`.
3. Reinstala OpenCV con ventanas: `python -m pip install --force-reinstall --no-deps opencv-contrib-python==4.11.0.86`.
4. Copia `.env.example` a `.env` si todavía no existe.
5. Configura `ROBOFLOW_API_KEY` y solamente las integraciones que utilizarás.

No guardes `.env` ni credenciales reales en el repositorio.

### Detector RF-DETR NAS v6

| Variable | Uso | Obligatoria |
|---|---|---|
| `CAMARA_RTSP_URL` | URL RTSP/HTTP completa | No; tiene prioridad sobre Tapo y webcam |
| `CAMARA_VENTANA` | Título de ventana en Windows (p. ej. `BlueStacks`) | No; tiene prioridad sobre `CAMARA_PC_INDICE` |
| `CAMARA_PC_INDICE` | Índice de webcam | Solo sin Tapo ni ventana; predeterminado `0` |
| `ROBOFLOW_MODEL_ID` | Model URL del modelo RF-DETR en Roboflow | No; usa `monitorninfas20/monitorninfas-6-rfdetr-nas-base-t1--c661c3` |
| `ROBOFLOW_API_KEY` | Private API Key con acceso al modelo; caché no garantiza omitir autenticación | Para el modelo de la plataforma |
| `RFDETR_WEIGHTS_PATH` | Checkpoint opcional del RF-DETR Base estándar (`rfdetr.RFDETRBase`); no implica compatibilidad con cualquier NAS | No; dejar vacío para el modelo de la plataforma |
| `MODEL_CACHE_DIR` | Caché de Inference | No; adaptador usa `.cache/roboflow` absoluta por defecto |
| `NINFAS_HEADLESS` | Ejecuta `main.py` sin ventana OpenCV (`1`) | No; útil en servidor mini dedicado |
| `NINFAS_AUDIO_RTSP` | Activa (`1`) o desactiva (`0`) segundo stream RTSP de audio | No; predeterminado `1` |
| `NINFAS_AUTO_DATASET` | Guarda frames dudosos (`1`) en `dataset/capturas_activas` | No; predeterminado `0` |
| `TAPO_USER` | Usuario local de cámara | Para RTSP Tapo |
| `TAPO_PASS` | Contraseña local de cámara | Para RTSP Tapo |
| `TAPO_IP` | IP de la cámara | Para RTSP Tapo |
| `ZONA_COMEDERO` | Polígono normalizado | No |
| `ZONA_BEBEDERO` | Polígono normalizado | No |
| `NINFAS_ZONAS_DINAMICAS` | Permite zonas dinámicas (`1`) o exige fijas (`0`) | No; predeterminado `1` |
| `NINFAS_SNAPSHOT_INTERVALO` | Segundos entre snapshots en SQL (mínimo `60`) | No; predeterminado `300` |
| `NINFAS_HORARIO_DIURNO` | Horario local observable, formato `08:00-20:00` | No; vacío usa la señal de color de la cámara |
| `AZURE_SERVER` | Host de Azure SQL | Para persistencia/panel |
| `AZURE_DATABASE` | Base de datos | Para persistencia/panel |
| `AZURE_USERNAME` | Usuario SQL | Para persistencia/panel |
| `AZURE_PASSWORD` | Contraseña SQL | Para persistencia/panel |
| `AZURE_DRIVER` | Driver ODBC | No; usa Driver 18 |
| `FOUNDRY_PROJECT_ENDPOINT` | Endpoint de proyecto | Para asistente |
| `FOUNDRY_API_KEY` | Clave Foundry | Para asistente |
| `FOUNDRY_MODEL` | Nombre de deployment/modelo | Para asistente |
| `NINFAS_AGENT_API_KEY` | Clave de herramientas | API externa/CLI |
| `NINFAS_AGENT_API_URL` | API reducida local | Cliente de consola |
| `NINFAS_AGENT_PUBLIC_URL` | URL HTTPS externa | Foundry remoto |
| `NINFAS_ADMIN_API_KEY` | Administración remota | No para localhost |
| `NINFAS_ALLOWED_HOSTS` | Hosts HTTP aceptados | Sí al publicar |
| `NINFAS_ENABLE_DOCS` | Activa `/docs` con valor `1` | No |
| `NINFAS_ALERT_WEBHOOK_URL` | Webhook HTTPS para alertas críticas (Discord/Slack) | No |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram para alertas clínicas | No |
| `TELEGRAM_CHAT_ID` | ID del chat de Telegram receptor de alertas | No |

Las claves de agente y administración deben tener al menos 32 caracteres. Una
forma de generarlas es:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Modos de operación

### Solo monitor local

Configura webcam o Tapo y ejecuta:

```powershell
python main.py
```

Sin las cuatro variables `AZURE_*`, el monitor muestra detecciones, estados y
alertas, pero no persiste eventos. El panel no tendrá una fuente de datos.

Para una cámara RTSP que no sea Tapo puedes definir directamente, sin imprimir
la credencial en los logs:

```env
CAMARA_RTSP_URL=rtsp://usuario:clave@192.168.1.100:554/ruta
```

### Monitor con Azure SQL

Instala Microsoft ODBC Driver 18, completa `AZURE_*`, respalda cualquier base
existente y ejecuta:

```powershell
python tools/migrar_bd.py
python main.py
```

`migrar_bd.py` crea `Aves`, `BitacoraAves`, claves e índices faltantes. Cada
archivo SQL se aplica una sola vez y queda registrado. No ejecutes el monitor y
una migración simultáneamente durante una actualización de producción.

### Panel

```powershell
uvicorn app.servidor:app --host 127.0.0.1 --port 8123
```

La administración y el asistente están permitidos sin clave únicamente si el
cliente es loopback. Las lecturas no requieren autenticación, por lo que el
servidor debe permanecer en una red de confianza si no hay un gateway delante.

### Asistente del panel

Completa `FOUNDRY_*` y abre el panel normal. `/api/asistente` invoca Foundry y
ejecuta sus herramientas de forma local; no requiere el puerto 8124.

### Asistente de consola o herramientas externas

```powershell
uvicorn app.servidor_agente:app --host 127.0.0.1 --port 8124
python -m app.agente_foundry "¿Cómo está Mushu hoy?"
```

El cliente envía `X-Ninfas-Agent-Key` a `NINFAS_AGENT_API_URL`.

## Configuración de zonas

Cada zona necesita al menos tres puntos `x,y` separados por `;`. Las
coordenadas se normalizan respecto del ancho y alto del frame:

```powershell
python tools/configurar_zonas.py --zona comedero
python tools/configurar_zonas.py --zona bebedero --fuente 1
```

La herramienta imprime la línea `ZONA_...` lista para copiar a `.env`.

```env
ZONA_COMEDERO=0.12,0.70;0.38,0.70;0.38,0.94;0.12,0.94
```

Para convertir un punto de píxeles `(x, y)`:

```text
x_normalizado = x / ancho_frame
y_normalizado = y / alto_frame
```

Usa polígonos sin superposición siempre que sea posible. Si una detección queda
en ambas zonas, la máquina no la clasifica como comida ni bebida.

Si una variable es inválida, el monitor la ignora y registra la causa; entonces
puede usar zonas dinámicas si detecta el plato correspondiente.

## Orden recomendado de inicio y cierre

1. Verifica que Azure sea accesible, si se utiliza.
2. Inicia `app.servidor` si necesitas panel.
3. Inicia `main.py`.
4. Comprueba video, IDs, zonas, audio y estado SQL.
5. Cierra el monitor con `q` antes de detener la API.

El cierre con `q` finaliza estados activos, vacía la cola SQL, detiene audio y
cámara y libera las ventanas de OpenCV. Evita terminar el proceso por la fuerza
si hay eventos pendientes.

## Exposición remota

No ejecutes Uvicorn directamente contra Internet. Utiliza un reverse proxy o
túnel que proporcione TLS y preserve correctamente el esquema HTTPS.

Configura, como mínimo:

```env
NINFAS_ADMIN_API_KEY=clave_larga
NINFAS_AGENT_API_KEY=otra_clave_larga
NINFAS_ALLOWED_HOSTS=ninfas.example
NINFAS_AGENT_PUBLIC_URL=https://ninfas.example
```

El backend rechaza claves administrativas por HTTP cuando la conexión no es
local. El host de `NINFAS_AGENT_PUBLIC_URL` se incorpora a los hosts permitidos.

## Solución de problemas

### El monitor usa webcam en vez de Tapo

Las tres variables `TAPO_USER`, `TAPO_PASS` y `TAPO_IP` deben existir. Verifica
que RTSP esté habilitado y que `/stream2` sea válido para ese modelo.

### Cámara sin señal

`CamaraStream` reintenta con backoff. Revisa IP, red, credenciales, otro cliente
que esté consumiendo el límite de streams y reglas de firewall.

### `Sin audio`

La webcam no se analiza. En RTSP, confirma que la cámara publique una pista de
audio. PyAV reintenta cada cinco segundos y conserva el último error interno.

### El tracking se desactiva

El monitor informa el error y continúa con detección simple. Revisa la
instalación de `lap`, Ultralytics y el archivo `botsort.yaml` distribuido por la
biblioteca.

### Error ODBC o Azure 503

- Instala ODBC Driver 18 con la misma arquitectura de Python.
- Comprueba `AZURE_SERVER`, firewall de Azure y credenciales.
- Ejecuta `python tools/migrar_bd.py`.
- En Windows puedes revisar drivers con `Get-OdbcDriver`.

### Respuesta 401

Falta una clave configurada o la enviada no coincide. Las claves no deben tener
menos de 32 caracteres.

### Respuesta 403

Puede indicar host/origen no permitido, operación remota sin clave o uso de
HTTP en administración remota.

### Respuesta 429

Se excedió el límite por IP. Respeta `Retry-After`; no implementes reintentos
agresivos desde el cliente.

### Verificación local

```powershell
python tools/verificar_proyecto.py
python -m unittest discover -s tests -v
```
