# Monitor de Ninfas para Android

Aplicación **nativa Kotlin/Jetpack Compose**, instalable mediante APK. Consulta
la API del proyecto; la cámara, RF-DETR y Azure SQL siguen en la PC. No se
incluyen claves de servicios en el APK.

## Compilar en esta PC

Desde la raíz del repositorio:

```powershell
.\android\build-android.ps1
```

El script busca Android Studio/JDK y SDK 36. Se pueden indicar `-SdkRoot`,
`-JavaHome` y `-GradleHome` si están en otra ruta. Gradle descarga dependencias
oficiales cuando faltan. Ejecuta compilación, pruebas JVM y lint; no instala
ni publica automáticamente.

En Windows, el script contempla el [fallo de caché de Gradle 8.14](https://github.com/gradle/gradle/issues/31438):
tras terminar el proceso solo renombra outputs de transformación completos que
no tienen destino, sin borrar ni sobrescribir cachés. Hace como máximo dos
reintentos si esa reparación realizó cambios; los fallos de pruebas siguen
propagándose como error.

APK resultante: `android/app/build/outputs/apk/debug/app-debug.apk`.
Está firmada con una clave local **de prueba**, guardada en
`.cache/android-signing/debug.keystore`. Conserva esa clave para actualizar
esta misma instalación. Una firma nueva requiere desinstalar la APK anterior,
con pérdida de sus ajustes locales. No es una firma para publicar en tienda.

El proyecto también se puede abrir desde `android/` en Android Studio. El
wrapper fijado permite `gradlew.bat assembleDebug`; se necesita SDK configurado
y la clave de prueba que prepara el script.

## Instalar la APK en tu Android

La copia preparada para esta entrega está en
`android/entrega/MonitorNinfas-1.0.0-prueba.apk` (18,2 MB).
La compilación y las 48 pruebas pasan. La APK ya está instalada en un Android
real y su conexión con la API está comprobada. Detalles:
`docs/ANDROID_VALIDACION_2026-11-18.md`.

1. Copia `MonitorNinfas-1.0.0-prueba.apk` al teléfono, por ejemplo mediante USB.
2. Abre el archivo en el teléfono y permite instalar aplicaciones desde la
   aplicación que lo abrió, cuando Android lo solicite.
3. Abre **Monitor de Ninfas**. Requiere Android 8 o posterior.

Con depuración USB y el teléfono autorizado también se puede instalar desde PC:

```powershell
adb devices
adb -s SERIAL_DEL_TELEFONO install -r android\app\build\outputs\apk\debug\app-debug.apk
```

Selecciona el serial explícitamente para evitar instalar en BlueStacks u otro
dispositivo conectado. La app no solicita permisos de cámara ni micrófono.

## Conectar dentro y fuera de casa

Tailscale está instalado en la PC y en Android, y Tailscale Serve está
configurado para dirigir HTTPS hacia la API local. En la app usa esta URL,
sin añadir `/api`:

```text
https://desktop-0fqurss.tailef3fb6.ts.net
```

La clave administrativa es `NINFAS_ADMIN_API_KEY` en el archivo `.env` de la
PC; su valor no se incluye en esta documentación. Introduce esa clave en la app
y pulsa **Comprobar conexión** y **Guardar conexión**. Las consultas de la APK
ya llegaron correctamente a la API. Quedan pendientes la prueba usando datos
móviles, los avisos con la app cerrada y las pruebas instrumentadas en dispositivo.

La API se inició en esta PC y escucha en `127.0.0.1:8123`. No se configuró su
inicio automático: después de reiniciar la PC, abre una terminal en la raíz
del proyecto y ejecuta:

```powershell
.\tools\iniciar_api_android.ps1 -ServerName desktop-0fqurss.tailef3fb6.ts.net
```

Si la API de este proyecto ya ocupa el puerto, el script muestra **«ya esta
ejecutandose»** y termina correctamente, manteniendo el servidor y la clave
existentes. Comprueba el proceso y que acepte el hostname indicado antes de
reutilizarlo. Si el puerto pertenece a otro programa o a un arranque con
`--app-dir` personalizado, informa del conflicto sin detener procesos.
Cuando el comando inicie una API nueva, mantén esa terminal abierta mientras
uses la app.

La API entrega los reportes guardados; el monitor `main.py` captura y analiza
la cámara para crear reportes nuevos. Que la APK conecte no significa que el
monitor esté activo: el aviso de monitor inactivo se observó cuando `main.py`
y BlueStacks estaban cerrados.

En esta sesión se inició el monitor con CUDA en segundo plano, con **BlueStacks
AppPlayer** abierto y la cámara conectada. El **18 de noviembre de 2026 a las
14:26, hora de Chile**, se comprobó un reporte real nuevo de las
`14:26:04.1-03:00`: `/api/health` respondió `status: ok`, base de datos disponible,
monitor activo y cero lotes pendientes. Todavía no se ha observado la
actualización de ese estado en la pantalla del teléfono.

Deja la cámara en vivo en BlueStacks para que el monitor reciba frames de esa
ventana. El snapshot periódico está configurado en **300 segundos (5 minutos)**
y solo se genera cuando el monitor procesa frames; el primer reporte no es inmediato.

Para arrancar el monitor manualmente después de reiniciar la PC, abre otra
terminal en la raíz del proyecto y ejecuta:

```powershell
.\.venv\Scripts\python.exe main.py
```

Mantén también esta terminal abierta y BlueStacks con la cámara en vivo.

La APK necesita una **URL HTTPS real accesible desde el teléfono**. Instalarla
no crea por sí mismo una dirección de Internet para tu PC. No uses
`http://127.0.0.1:8123` ni `localhost` en el teléfono.

Para recrear esta configuración, usa **Tailscale en PC y Android con la misma
cuenta**, más **Tailscale Serve** para HTTPS dentro de esa red privada. Sigue las
instrucciones oficiales de [Windows](https://tailscale.com/docs/install/windows)
y [Android](https://tailscale.com/docs/install/android).

1. Instala Tailscale en ambos equipos, inicia sesión y deja conectado el teléfono
   a esa red privada, también cuando estés fuera de casa.
2. Consulta el nombre completo de la PC en Tailscale, por ejemplo
   `mi-pc.mi-red.ts.net`. Sustituye este ejemplo por el nombre de tu PC.
3. En una terminal del proyecto inicia la API, sustituyendo el nombre:

   ```powershell
   .\tools\iniciar_api_android.ps1 -ServerName mi-pc.mi-red.ts.net -PrepararClave
   ```

   Prepara `NINFAS_ADMIN_API_KEY` en `.env` si falta o es demasiado corta y no
   modifica una clave válida. No imprime la clave. Permite ese hostname y
   escucha solamente en loopback, confiando el protocolo reenviado solo al proxy
   local. No ejecuta migraciones ni inicia el detector.

   Si la terminal tiene `NINFAS_ADMIN_API_KEY`, esa variable tiene prioridad
   sobre `.env`: usa esa misma clave en Android. Una variable heredada demasiado
   corta se rechaza antes de modificar el archivo.

4. En otra PowerShell como administrador, configura el proxy privado:

   ```powershell
   tailscale serve --bg http://127.0.0.1:8123
   tailscale serve status
   ```

   Sigue la indicación de Tailscale si pide habilitar HTTPS en tu red. Usa la
   URL HTTPS que muestre; Serve mantiene este acceso dentro de la red privada.

5. En la app introduce esa URL sin `/api`, la clave `NINFAS_ADMIN_API_KEY` de tu `.env` y
   pulsa **Comprobar conexión** y **Guardar conexión**. Copia solo esa clave,
   sin enviar el archivo `.env` ni sus credenciales por chat.

La [documentación de Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
explica su alcance privado. Restringe los miembros de tu red a dispositivos
autorizados: las lecturas de la API actual no llevan autenticación de usuario.
No publiques Uvicorn directamente para sustituir esta red privada.

La PC debe permanecer encendida, con API y monitor activos. Azure SQL almacena
los reportes; la app no se conecta directamente a SQL. La clave administrativa
habilita alta/baja de aves y asistente; con la clave ausente o incorrecta, el
servidor puede rechazar esas operaciones aunque las lecturas funcionen.

Otro proxy HTTPS privado o gateway autenticado también puede servir, pero su
configuración debe mantener las comprobaciones de host y protocolo del servidor.
No desactives la validación del certificado de la APK.

## Avisos con la app cerrada

Activa **Avisos con la app cerrada**, concede permiso de notificaciones y guarda.
WorkManager comprueba periódicamente, como mínimo cada 15 minutos; Android puede
retrasarlo según batería y restricciones. No son notificaciones push inmediatas.
Vuelve a abrir la app tras forzar su detención para restablecer los trabajos.

La primera consulta establece el estado inicial; no avisa por todo el historial.
Después avisa por nuevas recomendaciones de atención/urgencia y escaladas, sin
repetir el mismo aviso porque cambien sus horas. No genera avisos con el monitor
sin reporte fresco o por un simple fallo de red. Los datos antiguos permanecen
señalados al abrir la aplicación. Desactivar avisos o borrar la conexión cancela
el trabajo correspondiente.

La clave se cifra mediante Android Keystore y se excluye de backup/transferencia.
Cambiar de servidor elimina la clave anterior y los datos/avisos locales; hay
que introducir la clave de ese servidor. Esto no borra los reportes de Azure.

## Pantallas

- **Inicio:** estado global de la jaula y recomendaciones de las últimas 24 h.
- **Historial:** ánimo, actividad, visitas y rangos 6 h / 24 h / 7 días.
- **Mis ninfas:** catálogo, altas/bajas confirmadas y estadísticas individuales.
- **Asistente:** preguntas independientes basadas en reportes, mediante Foundry.

Se actualiza al regresar, manualmente y cada 60 s mientras está abierta. Una
petición fallida no se repite automáticamente si podía crear/eliminar un ave o
generar una consulta al asistente. Ánimo/audio/actividad describen la jaula,
no a cada ave; las visitas observadas no prueban ingesta efectiva.

No se incluyen video en directo ni control remoto de encendido del monitor,
porque la API actual no dispone de esas funciones.
