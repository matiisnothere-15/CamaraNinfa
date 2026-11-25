# Validación de la APK — 18 de noviembre de 2026

## Alcance

APK nativa Kotlin/Compose para Android 8 o posterior, paquete
`cl.ninfas.monitor`, versión `1.0.0`. Incluye estado, historial, estadísticas,
catálogo de aves, asistente y avisos periódicos. Cámara, detector y SQL siguen
en la PC. Después de entregar e instalar la APK, el propietario completó la
conexión de Tailscale y la habilitación HTTPS. La API ya está accesible dentro
de esa red privada.

## Comprobaciones

- Compilación real `assembleDebug`: APK generada y firma de prueba verificada
  mediante Android SDK (`apksigner`).
- `assembleDebug`, `testDebugUnitTest` y `lintDebug`: `BUILD SUCCESSFUL`.
  Pasan las 48 pruebas: 45 de cliente HTTPS, parsing, conexión, avisos y
  utilidades, más 3 de pantallas con Robolectric Android 35.
- Capturas nativas de Inicio, gráficos de historial y Asistente generadas en
  `android/app/build/screenshots/` e inspeccionadas visualmente. Los tests
  comprueban datos ausentes/degradados, selección accesible de gráficos y
  límites de texto/envío único del asistente, con datos ficticios.
- Lint: 0 errores y 27 advertencias, sobre versiones de dependencias y
  recomendaciones de estilo/API. No se deshabilitaron reglas para aprobarlo.
- `assembleDebugAndroidTest`: compila el APK de pruebas de Keystore real;
  esas dos pruebas instrumentadas no se ejecutaron por falta de dispositivo.
- Las comprobaciones Python específicas de backup, clave heredada y arranque
  pasan: 10 pruebas y 5 subpruebas, usando temporales en `.cache/test-temp`.
- Ruff completo y `git diff --check`: sin errores.
- Revisión independiente del código, transporte HTTPS, cambio de servidor,
  cifrado y avisos: corregidos los dos hallazgos sobre exclusión de backups y
  prioridad de una clave de entorno heredada demasiado corta.
- Manifiesto del APK inspeccionado: mínimo API 26, destino API 36,
  backup y tráfico HTTP desactivados; sin permisos de cámara/micrófono.
  El archivo no contiene `.env`, keystores ni pesos de modelos.

## Archivo entregado

`android/entrega/MonitorNinfas-1.0.0-prueba.apk`, 18 247 827 bytes.
La copia coincide con el APK compilado y verifica firma v2.

SHA-256:
`626C7EA44B1390E3A4534489F721729EBDAE4E6BC93AC313912FBDA878178B6D`.

## Límites de la verificación

Al compilar no había teléfono conectado por ADB. El propietario confirmó que
instaló y abrió la APK; su Android aparece conectado en Tailscale. Los registros
de la API confirman consultas del Android a los siete endpoints, todas HTTP 200;
el aviso de monitor inactivo es de salud del monitor, no de conexión. El emulador independiente falla en el
proceso nativo QEMU antes de arrancar Android; no se modificaron BlueStacks,
características de Windows ni la cámara para resolverlo. Quedan pendientes las
pruebas instrumentadas de Keystore real y avisos en segundo plano. Las pruebas
de pantallas usan Robolectric y datos ficticios.

Los avisos usan WorkManager con
intervalo mínimo de 15 minutos, sujeto a restricciones de Android; no son push
inmediatos.

## Conexión real comprobada

- URL base: `https://desktop-0fqurss.tailef3fb6.ts.net`, sin `/api`.
- Tailscale: PC y Android conectados, capacidad HTTPS habilitada y dominio de
  certificado disponible. Serve dirige HTTPS de puerto 443 a
  `http://127.0.0.1:8123`; no se habilitó Funnel.
- API en segundo plano, escuchando exclusivamente en `127.0.0.1:8123`.
  Logs locales en `.cache/android-server/`. No se configuró autoarranque de la
  API: consultar `android/README.md` para iniciarla después de reiniciar la PC.
- Solicitudes reales a la URL HTTPS con validación normal del certificado:
  `/api/health` y `/api/aves` respondieron HTTP 200; catálogo de 2 aves.
- Tras abrir la cámara, la comprobación del 18 de noviembre a las 14:26 de
  Chile devolvió `status=ok`, Azure SQL disponible, `monitor_activo=true`,
  último snapshot `14:26:04.100` y 0 lotes pendientes.
  Conectar la app no inicia por sí mismo la cámara.
- Se comprobó que `main.py` y BlueStacks estaban cerrados. Se inició el monitor
  en segundo plano, con `NINFAS_HEADLESS=1` solo en su proceso, RF-DETR cargado
  y proveedores CUDA/CPU disponibles. `.env` permanece sin cambios.
  El propietario abrió la cámara en vivo y se confirmó la ventana configurada
  `BlueStacks App Player`, cámara conectada y un snapshot nuevo persistido.
  El intervalo configurado es 300 s; no se guarda snapshot sin imagen reciente.
- Control administrativo comprobado sobre HTTPS mediante `POST /api/aves`
  con cuerpo deliberadamente incompleto `{}`: clave incorrecta → 401; clave
  configurada → 422 por faltar `nombre`. No se creó ni eliminó ningún ave.
- Clave referida por nombre `NINFAS_ADMIN_API_KEY` en `.env`; su valor no se
  imprimió ni se copió a documentación, APK o chat.
- La PC y Tailscale deben permanecer activos para acceder desde el teléfono.
  El acceso con datos móviles y los avisos con la app cerrada aún necesitan
  comprobación en el dispositivo del propietario.

La firma es de prueba. Conservar `.cache/android-signing/debug.keystore` para
poder actualizar la misma instalación. No se ha publicado en Google Play ni
hecho commit/push de los cambios de esta sesión.

## Reejecución del arranque de la API

El error Windows 10048 se reprodujo al intentar iniciar otra API sobre el
puerto 8123, ya ocupado por la instancia de este proyecto. Se corrigió
`tools/iniciar_api_android.ps1` para comprobar primero el listener y el proceso,
incluido el redirector de Python virtual en Windows. Si reconoce la API del
proyecto en loopback y acepta el hostname, informa que ya está ejecutándose
y sale correctamente antes de preparar claves o invocar otro Python.

Puertos de otros procesos, otro entorno virtual, listeners fuera de loopback,
padre con PID reutilizado y arranques con `--app-dir` personalizado se rechazan
sin iniciar/detener procesos. El probe es GET `/` local con Host, sin consultar
SQL ni enviar credenciales. `-Comprobar` mantiene la comprobación de configuración.

Se observaron primero los fallos de regresión y luego 10 pruebas/5 subpruebas
aprobadas. La prueba real con Windows PowerShell terminó con código 0, conservó
PID 14900 y `.env` intactos. La API HTTPS siguió respondiendo `status=ok`,
monitor activo y Azure SQL disponible. Ruff y diff sin errores. No se cambió
la APK ni la lógica de cámara/SQL.

La suite Python completa de esta revisión terminó con 217 pruebas y 41
subpruebas aprobadas, más una subprueba fallida en
`test_reintento_conserva_linea_corrupta_y_lotes_posteriores_en_orden`
(`tests/test_base_datos.py:247`). El test aislado pasó en ambos subcasos.
No se confirmó la causa; el resultado es compatible con un error al
reemplazar el archivo temporal de respaldo. No se modificó esa lógica y no se
declara corregida esa incidencia.

## Hallazgo separado en el monitor

La suite Python completa dio 208 pruebas aprobadas, 1 fallo y 39 subpruebas
aprobadas. El fallo corresponde a
`test_evidencia_evento_rota_archivos_antiguos_al_superar_cuota`, fuera del módulo
Android. Una reproducción con barrera confirmó una carrera previa: un JPG ya
escrito sigue contado como archivo en vuelo y la rotación del siguiente
despacho lo cuenta dos veces. Puede borrar evidencias de más.

El test aislado puede pasar; repetirlo no elimina la carrera. La reparación
propuesta es que, en modo asíncrono con rotación, rote exclusivamente el worker
serial antes de escribir. No se cambió esa lógica al preparar la APK, conforme
a la prioridad de entrega y al aislamiento del módulo Android.

## Instalación

Consultar `android/README.md`. El propietario ya instaló la APK y la conexión
con la API está comprobada. Para datos en vivo también necesita mantener
abierta la cámara en BlueStacks y ejecutar el monitor de la PC.
