# Entrega técnica y trabajo pendiente

Fecha del estado: 12 de julio de 2026.

> Documento histórico. El detector predeterminado pasó a RF-DETR NAS en noviembre.
> Las métricas YOLO de julio no corresponden al JSON de evaluación actual,
> que fue generado el 16 de noviembre para otro checkpoint. Consulta la
> [revisión de noviembre](REVISION_2026-11-17.md) para el estado actual.

Este documento resume lo realizado en el Monitor de Ninfas, lo que fue
validado localmente y las tareas que todavía requieren la cámara, Azure u otro
entorno externo. No contiene credenciales reales.

## Resumen ejecutivo

El código y sus componentes aislados están terminados y validados. El modelo
actual se cargó realmente y fue evaluado sobre el test agrupado. Sin embargo,
la solución todavía necesita una prueba de integración completa con la cámara,
Azure SQL y Microsoft Foundry reales antes de considerarse lista para uso
continuo o despliegue público.

| Área | Estado | Observación |
|---|---|---|
| Código Python | Completado | 91 pruebas aprobadas y Ruff limpio |
| YOLO y Supervision | Completado localmente | Checkpoint cargado y evaluado en CPU |
| Dataset | Completado con advertencias | Sin fugas; todavía es pequeño |
| Webcam/RTSP real | Pendiente | No se contó con la cámara del usuario |
| Zonas reales | Pendiente | Deben marcarse sobre la imagen definitiva |
| Azure SQL | Pendiente | Sin `.env`, credenciales ni ODBC Driver detectado |
| Migraciones Azure | Pendiente | No se ejecutaron contra una base real |
| Microsoft Foundry | Pendiente | Sin endpoint, deployment ni API key reales |
| Prueba prolongada | Pendiente | Falta validar varias horas de operación |
| Despliegue público | Pendiente | Falta infraestructura TLS, identidad y monitoreo |

## Trabajo realizado

### 1. Revisión y reorganización

- Se revisaron los módulos activos, prototipos históricos, herramientas,
  frontend, SQL, dataset y documentación.
- Se eliminó la implementación duplicada `modulos/identificacion.py` y se dejó
  `IdentificadorColor` como única fuente de identidad individual.
- Se separaron responsabilidades entre captura, inferencia, comportamiento,
  persistencia, API y asistente.
- Se agregó un verificador liviano en `tools/verificar_proyecto.py`.

### 2. Captura de cámara y audio

- `CamaraStream` conserva el frame más reciente para evitar retrasos acumulados.
- Se agregó reconexión con backoff y publicación explícita de errores.
- Se centralizó la selección de fuente en `modulos/fuente_video.py`.
- Se admiten webcam, URL RTSP/HTTP genérica y configuración Tapo.
- Las descripciones de la fuente ocultan usuario y contraseña.
- El audio RTSP usa PyAV; con webcam se utiliza un monitor nulo.
- Las herramientas de cámara ya no contienen una IP personal fija.

Herramientas disponibles:

```powershell
python tools/escaner_camara.py --escanear
python tools/escaner_camara.py --fuente 0
python tools/recolector_fotos.py --fuente 0 --total 50 --intervalo 5
```

### 3. Visión con Ultralytics y Supervision

- Ultralytics carga `best.pt` y ejecuta detección o tracking con BoT-SORT.
- Supervision 0.29.1 convierte las salidas a `Detections`, filtra resultados,
  dibuja cajas, etiquetas y trazas, y evalúa `PolygonZone`.
- Se mantuvo un solo tracker para no producir IDs contradictorios.
- Si BoT-SORT falla, el monitor continúa con detección simple.
- Se validan confianza y área de las clases `ninfa`, `comedero` y `bebedero`.

### 4. Comportamiento e identidad

- Se implementó una máquina de estados independiente por `track_id`.
- Estados disponibles: activo, inactivo, comiendo, bebiendo y desconocido.
- Confirmaciones actuales: 1 s para actividad, 2 s para comer/beber y 10 s
  para inactividad.
- Una pérdida de tracking de hasta 3 s no cierra inmediatamente el evento.
- Una superposición entre comedero y bebedero se considera ambigua.
- La identidad por color requiere votos consistentes y evita asignar el mismo
  nombre a dos tracks.
- En imagen infrarroja o sin color no se inventa una identidad.

### 5. Movimiento, salud y recomendaciones

- El movimiento se normaliza por la diagonal del frame para no depender de la
  resolución.
- Se restauran desde SQL los últimos consumos conocidos al reiniciar.
- Se generan alertas por períodos prolongados sin comida o agua observada.
- Las recomendaciones distinguen niveles informativo, atención y urgente.
- Los estados y recomendaciones son heurísticos, no diagnósticos veterinarios.

### 6. Persistencia y migraciones

- Se centralizó Azure SQL en `modulos/base_datos.py`.
- Las consultas usan parámetros y rollback ante errores.
- El monitor escribe mediante una cola FIFO con un solo escritor.
- Las operaciones relacionadas se agrupan en transacciones.
- Se prepararon migraciones idempotentes y versionadas:

  - `001_schema_base.sql`: crea `Aves` y `BitacoraAves`;
  - `002_upgrade_tracking_indexes.sql`: agrega columnas, relación, restricciones
    e índices;
  - `SchemaMigrations`: registra cada archivo aplicado.

### 7. API, panel y seguridad

- Se implementaron APIs para estado, historial, acciones, recomendaciones,
  estadísticas y administración de aves.
- Se corrigió el tratamiento de errores SQL para responder 503 sin filtrar
  detalles internos.
- Se añadieron validación Pydantic, límites de cuerpos y rate limiting.
- Se añadieron CSP, protección de hosts, cabeceras HTTP y escape de datos.
- Las operaciones sensibles solo se aceptan desde localhost cuando no hay una
  clave administrativa.
- Para acceso remoto se exige HTTPS y una clave de al menos 32 caracteres.

### 8. Asistente Microsoft Foundry

- Se integró la Responses API mediante el SDK de OpenAI configurado con el
  endpoint del proyecto de Microsoft Foundry.
- El asistente solo puede ejecutar dos herramientas de lectura:

  - `obtener_estado_ave`;
  - `obtener_recomendaciones_monitor`.

- No recibe credenciales SQL ni puede ejecutar funciones Python arbitrarias.
- Se limitaron pregunta, respuesta, rondas y cantidad de llamadas.
- Los datos recuperados se tratan como contenido no confiable.

### 9. Dataset, entrenamiento y evaluación

- Se reconstruyeron splits agrupados para evitar fotogramas de una misma fuente
  en train, validación y test.
- El dataset lógico contiene 178 imágenes, 138 fuentes y 605 objetos.
- La auditoría no encontró fuentes repetidas, duplicados exactos ni pares
  visualmente casi idénticos entre splits.
- Se prepararon scripts reproducibles de auditoría, entrenamiento y evaluación.
- Las métricas antiguas quedaron marcadas como históricas y no comparables.
- `best.pt` se evaluó sobre el nuevo test sin entrenarlo ni reemplazarlo.

Resultados actuales:

| Clase | Precisión | Recall | F1 | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| Bebedero | 0.636 | 0.941 | 0.759 | 0.758 | 0.604 |
| Comedero | 0.596 | 0.591 | 0.593 | 0.510 | 0.401 |
| Ninfa | 0.709 | 0.794 | 0.749 | 0.828 | 0.630 |
| Global | 0.647 | 0.775 | — | 0.699 | 0.545 |

El comedero es la clase con más margen de mejora. El test solo tiene 20
imágenes, por lo que estas métricas son una línea base, no una garantía de
producción.

### 10. Calidad y documentación

- 91 pruebas unitarias y estructurales aprobadas.
- Ruff sin observaciones.
- Dependencias instaladas sin conflictos en el entorno de validación.
- Checkpoint verificado mediante contenedor, metadatos y SHA-256.
- Smoke test correcto de imports, FastAPI, CSP y Supervision.
- JavaScript embebido del panel con sintaxis válida.
- README, arquitectura, operación, seguridad, entrenamiento y validación
  quedaron documentados.

## Estado comprobado del equipo actual

Al preparar esta entrega se comprobó lo siguiente:

- no existe un archivo `.env` en la raíz;
- Windows no detecta Microsoft ODBC Driver for SQL Server;
- no se proporcionaron credenciales de Azure SQL;
- no se proporcionaron credenciales de Microsoft Foundry;
- no se tuvo acceso a la cámara real.

Por seguridad, `.env` debe permanecer excluido del repositorio. También se
dejó `.env.example` con integraciones opcionales vacías para que copiarlo no
active por accidente una conexión ficticia.

## Pendiente obligatorio para la primera integración completa

### A. Preparar el entorno definitivo

Usar preferentemente Python 3.11, que es la versión objetivo documentada:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Generar claves distintas de al menos 32 caracteres:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

No copiar valores reales a `.env.example`, documentos, capturas o Git.

### B. Configurar y probar la cámara real

Elegir solo uno de estos modos en `.env`.

Webcam:

```env
CAMARA_PC_INDICE=0
CAMARA_RTSP_URL=
TAPO_USER=
TAPO_PASS=
TAPO_IP=
```

RTSP genérico:

```env
CAMARA_RTSP_URL=rtsp://usuario:clave@IP:554/ruta
```

Tapo:

```env
TAPO_USER=usuario_local_de_camara
TAPO_PASS=contrasena_local_de_camara
TAPO_IP=192.168.1.100
```

Comprobar la fuente antes de iniciar YOLO:

```powershell
python tools/escaner_camara.py --fuente 0
python tools/escaner_camara.py --fuente "rtsp://usuario:clave@IP:554/ruta"
```

Criterios de aceptación:

- la imagen se mantiene estable y con latencia razonable;
- una desconexión temporal se recupera sin reiniciar el proceso;
- una URL con credenciales no aparece completa en los logs;
- en RTSP se confirma si existe una pista de audio utilizable;
- la ventana se cierra limpiamente con `q`.

### C. Configurar zonas sobre la imagen definitiva

La posición cambia según cámara, resolución y encuadre. Generar ambas zonas:

```powershell
python tools/configurar_zonas.py --zona comedero
python tools/configurar_zonas.py --zona bebedero
```

Copiar los valores impresos a `.env`:

```env
ZONA_COMEDERO=0.12,0.70;0.38,0.70;0.38,0.94;0.12,0.94
ZONA_BEBEDERO=0.58,0.70;0.82,0.70;0.82,0.94;0.58,0.94
```

Evitar polígonos superpuestos y comprobar videos con el ave en el borde de
cada zona. Confirmar manualmente que permanecer en la zona representa comer o
beber; el sistema todavía no detecta contacto del pico ni ingesta efectiva.

### D. Instalar y configurar Azure SQL

Las migraciones no se ejecutaron sobre Azure porque este entorno no tiene
credenciales ni el controlador ODBC del sistema operativo.

1. Instalar Microsoft ODBC Driver 18 for SQL Server con la misma arquitectura
   que Python.
2. Reiniciar la terminal y verificar el driver:

```powershell
Get-OdbcDriver | Where-Object Name -Like "*ODBC Driver*for SQL Server*"
```

3. Crear o seleccionar la Azure SQL Database.
4. Autorizar en el firewall de Azure únicamente la IP o red del backend.
5. Respaldar la base si ya contiene información.
6. Completar `.env`:

```env
AZURE_SERVER=servidor.database.windows.net
AZURE_DATABASE=NinfasDB
AZURE_USERNAME=usuario_sql
AZURE_PASSWORD=contrasena_sql
AZURE_DRIVER={ODBC Driver 18 for SQL Server}
```

7. Ejecutar las migraciones desde la raíz:

```powershell
python tools/migrar_bd.py
```

La primera ejecución debería informar:

```text
Migraciones aplicadas:
- 001_schema_base.sql
- 002_upgrade_tracking_indexes.sql
```

Una segunda ejecución debe ser idempotente:

```text
La base de datos ya está actualizada.
```

8. Verificar desde el editor de consultas de Azure:

```sql
SELECT Nombre, AplicadaEn
FROM dbo.SchemaMigrations
ORDER BY AplicadaEn;

SELECT OBJECT_ID('dbo.Aves') AS Aves,
       OBJECT_ID('dbo.BitacoraAves') AS BitacoraAves;

SELECT name
FROM sys.indexes
WHERE object_id IN (OBJECT_ID('dbo.Aves'), OBJECT_ID('dbo.BitacoraAves'))
ORDER BY name;
```

9. Siempre que sea posible, migrar con una cuenta que tenga permisos DDL y
   luego configurar la aplicación con una cuenta de lectura/escritura mínima.

Criterios de aceptación:

- las dos migraciones figuran una sola vez;
- existen tablas, relación `AveId` e índices;
- `Encrypt=yes` conecta sin desactivar la validación del certificado;
- el monitor escribe eventos y los recupera después de reiniciarse;
- una caída temporal de SQL no bloquea indefinidamente el video;
- el cierre con `q` vacía la cola pendiente.

### E. Registrar las aves y validar identidad

Después de migrar, iniciar el panel:

```powershell
uvicorn app.servidor:app --host 127.0.0.1 --port 8123
```

Registrar a Yukki y Mushu desde el panel, usando descripciones distinguibles,
por ejemplo `amarilla lutino` y `gris plomo`. También puede utilizarse la API
desde localhost:

```powershell
$yukki = @{nombre="Yukki"; color="amarilla lutino"; notas=""} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8123/api/aves `
  -ContentType application/json -Body $yukki
```

Repetir con Mushu. Verificar:

- los nombres no se intercambian constantemente;
- un nombre no aparece en dos tracks a la vez;
- con infrarrojo se muestra incertidumbre en vez de una identidad falsa;
- oclusiones y cruces no generan una atribución persistente incorrecta.

### F. Ejecutar una prueba completa y prolongada

Con Azure y cámara configurados:

```powershell
python main.py
```

Realizar primero una sesión controlada de 15 a 30 minutos y luego una sesión de
varias horas. Preparar una hoja manual con hora real y comportamiento observado
para compararla con `BitacoraAves`.

Revisar como mínimo:

- detecciones correctas de ave, comedero y bebedero;
- estabilidad de `track_id`;
- inicio y fin de comer, beber, movimiento e inactividad;
- falsos positivos al pasar cerca de un plato;
- recuperación de cámara, red y SQL;
- consumo de CPU/GPU, memoria, FPS y temperatura del equipo;
- crecimiento de la base y latencia del panel;
- cierre limpio y recuperación de contadores al reiniciar.

### G. Configurar y probar Microsoft Foundry

Crear o seleccionar un proyecto/deployment en Microsoft Foundry y completar:

```env
FOUNDRY_PROJECT_ENDPOINT=https://recurso.services.ai.azure.com/api/projects/proyecto
FOUNDRY_API_KEY=clave_real
FOUNDRY_MODEL=nombre_del_deployment
NINFAS_AGENT_API_KEY=clave_aleatoria_de_32_o_mas_caracteres
```

Para el asistente incluido en el panel basta con iniciar el servidor principal:

```powershell
uvicorn app.servidor:app --host 127.0.0.1 --port 8123
```

Preguntas de aceptación sugeridas:

- `¿Cómo está Mushu hoy?`
- `¿Cuándo fue la última vez que Yukki comió?`
- `¿Qué recomendaciones tiene el monitor?`
- `¿Cómo está un ave que no existe?`

Comprobar que la respuesta se basa en SQL, que una ave inexistente se maneja
sin inventar datos y que ninguna credencial aparece en la respuesta o logs.

Para el cliente de consola o herramientas externas:

```powershell
uvicorn app.servidor_agente:app --host 127.0.0.1 --port 8124
python -m app.agente_foundry "¿Cómo está Mushu hoy?"
```

Si Foundry necesita llamar desde Internet, no publicar Uvicorn directamente.
Configurar un endpoint HTTPS y completar `NINFAS_AGENT_PUBLIC_URL`.

## Pendiente para mejorar el modelo

El detector funciona, pero todavía no tiene suficiente diversidad para afirmar
que generaliza a producción.

Prioridades:

1. Recolectar más ejemplos de `comedero`, especialmente con oclusiones,
   recipientes vacíos, reflejos y fondos parecidos.
2. Capturar otros días, horarios, iluminaciones, ángulos y estados de la jaula.
3. Crear un holdout externo de al menos 50 imágenes no correlacionadas.
4. Revisar manualmente polígonos y cajas antes de cada entrenamiento.
5. Mantener las fuentes agrupadas al regenerar splits.
6. Evaluar además en videos completos, no solo imágenes estáticas.

Flujo recomendado:

```powershell
python tools/recolector_fotos.py --total 100 --intervalo 3
python tools/crear_splits_agrupados.py
python tools/auditar_dataset.py --salida entrenamiento/dataset_report.json
python tools/entrenar_modelo.py
python tools/evaluar_modelo.py `
  --modelo runs/entrenamiento/NOMBRE/weights/best.pt `
  --split test `
  --salida entrenamiento/evaluaciones/nuevo_modelo_test.json
```

No reemplazar `best.pt` solamente porque un entrenamiento finalice. Exigir:

- auditoría sin fugas;
- mejora clara de `comedero` frente a mAP50-95 `0.401`;
- ausencia de una regresión importante en ninfa y bebedero;
- evaluación sobre el mismo test trazable;
- revisión satisfactoria en video real.

## Pendiente antes de un despliegue público

Estas tareas no son necesarias para una demo local, pero sí para publicar el
sistema o permitir varios usuarios:

- proxy o gateway HTTPS delante de Uvicorn;
- proveedor de identidad, sesiones y roles en vez de una clave compartida;
- autorización también para rutas de lectura sensibles;
- secretos en Azure Key Vault o identidad administrada;
- rate limiting centralizado para varios workers;
- logs estructurados, rotación, métricas y alertas de 5xx;
- copias de seguridad y simulacro de restauración de Azure SQL;
- auditoría de quién crea, edita o elimina aves;
- política de retención de videos, imágenes y eventos;
- revisión de privacidad y consentimiento si la cámara capta personas;
- pruebas de seguridad y carga;
- pipeline de integración continua para pruebas y Ruff;
- archivo `LICENSE` para definir cómo puede reutilizarse el código.

No hay actualmente `Dockerfile`, `docker-compose.yml` ni workflows de CI. No
son obligatorios para ejecutar localmente, pero deben decidirse según el modo
de despliegue elegido.

## Lista de cierre

### Primera demo con datos reales

- [ ] Instalar ODBC Driver 18.
- [ ] Crear `.env` y completar solo las integraciones utilizadas.
- [ ] Probar la cámara y su reconexión.
- [ ] Configurar comedero y bebedero.
- [ ] Respaldar y migrar Azure SQL.
- [ ] Registrar a Yukki y Mushu.
- [ ] Ejecutar el monitor y confirmar eventos en SQL.
- [ ] Abrir el panel y comprobar todas las vistas.
- [ ] Configurar Foundry y probar preguntas de aceptación.
- [ ] Ejecutar una sesión prolongada y revisar falsos positivos.

### Antes de producción

- [ ] Ampliar dataset y holdout externo.
- [ ] Validar umbrales y recomendaciones con un profesional veterinario.
- [ ] Definir infraestructura HTTPS y autenticación.
- [ ] Implementar secretos administrados, logs, alertas y backups.
- [ ] Ejecutar pruebas de seguridad, carga y recuperación.
- [ ] Añadir CI y licencia del código.

## Comandos de control después de cualquier cambio

```powershell
python tools/verificar_proyecto.py
python tools/auditar_dataset.py
pytest
ruff check main.py app modulos tools tests
```

Documentos relacionados:

- [Arquitectura](ARQUITECTURA.md)
- [Configuración y operación](CONFIGURACION_Y_OPERACION.md)
- [Entrenamiento y evaluación](ENTRENAMIENTO_Y_EVALUACION.md)
- [Seguridad](SEGURIDAD.md)
- [Validación final](VALIDACION_FINAL_2026-07-12.md)
