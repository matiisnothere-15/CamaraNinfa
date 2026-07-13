# Seguridad

## Alcance y modelo de amenaza

El backend maneja credenciales de cámara, Azure SQL, Microsoft Foundry y dos
claves internas. Los riesgos principales son:

- filtración de secretos en Git, navegador, logs o errores HTTP;
- acceso remoto no autorizado a mutaciones o llamadas con costo;
- XSS almacenado mediante nombres, colores, notas o respuestas;
- CSRF/orígenes cruzados;
- abuso por cuerpos o frecuencia de solicitudes;
- SQL injection;
- prompt injection mediante datos recuperados por herramientas;
- exposición directa de Uvicorn sin TLS ni gateway.

Los controles actuales están pensados para una instalación personal o de red
privada. No constituyen una plataforma de identidad multiusuario.

## Secretos

Variables sensibles:

- `TAPO_USER`, `TAPO_PASS`;
- `AZURE_USERNAME`, `AZURE_PASSWORD`;
- `FOUNDRY_API_KEY`;
- `NINFAS_AGENT_API_KEY`;
- `NINFAS_ADMIN_API_KEY`.

`.env` y `config/credenciales.py` están ignorados por Git. `.env.example` solo
contiene marcadores. No copies secretos a HTML, JavaScript, consultas del
asistente, capturas o informes de error.

Las claves internas deben tener al menos 32 caracteres y ser diferentes entre
sí. Rótalas después de una exposición y reinicia los procesos que cargan `.env`.

## Autorización

### Panel

Las rutas de lectura permanecen sin autenticación. Las siguientes operaciones
usan `_proteger_operacion_panel`:

- crear, editar o eliminar aves;
- consultar `/api/asistente`.

Sin `NINFAS_ADMIN_API_KEY`, solo se aceptan desde loopback. Con clave
configurada, el navegador la solicita y la mantiene exclusivamente en memoria.
No se guarda en cookies, `localStorage` ni `sessionStorage`.

Para clientes remotos, el backend exige esquema HTTPS. También valida `Origin`
y rechaza `Sec-Fetch-Site: cross-site`.

### Herramientas del agente

`/agent/estado-ave` y `/agent/recomendaciones` requieren
`X-Ninfas-Agent-Key`. La comparación usa `hmac.compare_digest`. La API reducida
del puerto 8124 publica las mismas dos operaciones y nada de escritura.

La especificación OpenAPI del agente declara el esquema `apiKey`, pero no
incluye el valor de la clave.

## Seguridad HTTP

`app.seguridad_http` instala:

- `TrustedHostMiddleware` con `NINFAS_ALLOWED_HOSTS`;
- límite real de 16 KiB para cuerpos POST, PUT y PATCH;
- `Content-Security-Policy` con hash SHA-256 del script inline del panel;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- `Permissions-Policy` sin cámara, micrófono ni geolocalización;
- `X-Frame-Options: DENY` y `frame-ancestors 'none'`;
- `Cache-Control: no-store` para API y agente.

La CSP permite estilos inline porque el panel genera colores y SVG dinámicos,
pero no permite scripts inline arbitrarios. Cambiar el bloque JavaScript cambia
automáticamente el hash calculado al iniciar la API.

## Rate limiting

Límites actuales por IP y ventana móvil de 60 segundos:

| Grupo | Solicitudes/minuto |
|---|---:|
| Página y estáticos | 300 |
| Lecturas `/api/*` | 240 |
| Escrituras `/api/*` | 30 |
| `/api/asistente` | 8 |
| API `/agent/*` o servidor de agente | 60 |

Una respuesta 429 incluye `Retry-After`. El estado vive en memoria: no se
comparte entre workers ni servidores. Para escalar horizontalmente se necesita
un limitador central en proxy, Redis u otro servicio.

## Validación y XSS

- Los modelos Pydantic rechazan campos extra y limitan longitudes.
- IDs y ventanas horarias tienen rangos explícitos.
- Textos se normalizan en Unicode y se eliminan caracteres de control.
- El frontend escapa los valores antes de incorporarlos a plantillas HTML.
- No existen handlers `onclick` construidos con contenido de la base.
- Las respuestas del asistente se asignan con `textContent`.
- Errores SQL públicos son genéricos; los detalles quedan en logs del servidor.

## Azure SQL

Todas las consultas variables utilizan parámetros `?`; no se interpolan
nombres, preguntas ni IDs dentro del SQL. El repositorio serializa el uso de la
conexión, hace rollback ante error y ofrece transacciones para mutaciones
relacionadas.

La cadena fuerza `Encrypt=yes` y `TrustServerCertificate=no`. El driver y el
sistema operativo deben confiar en la cadena de certificados de Azure.

Las migraciones son código con privilegios de esquema. Ejecútalas con una
cuenta separada cuando sea posible y usa para la aplicación una cuenta con los
permisos mínimos de lectura/escritura.

## Microsoft Foundry

El modelo no puede elegir funciones Python arbitrarias. Solo se aceptan dos
nombres de herramienta y argumentos acotados. Hay como máximo cuatro rondas de
herramientas y ocho llamadas en una ronda. La respuesta final se limita a 4.000
caracteres y la pregunta a 600.

Las instrucciones indican que nombres, colores y textos de herramientas son
datos no confiables. Esto reduce, pero no elimina, prompt injection. No añadas
una herramienta de escritura sin autorización independiente y confirmación de
usuario.

La implementación actual utiliza una API key. Para producción en Azure debe
evaluarse identidad administrada o credenciales de corta duración.

## Despliegue remoto

Lista mínima:

1. Proxy o túnel HTTPS delante de Uvicorn.
2. `NINFAS_ALLOWED_HOSTS` limitado al dominio real.
3. Claves distintas, aleatorias y rotadas.
4. Puerto SQL no expuesto a Internet; firewall limitado al backend.
5. Uvicorn enlazado a loopback o red privada detrás del proxy.
6. Documentación interactiva desactivada.
7. Logs protegidos, rotados y sin secretos.
8. Copias de seguridad y cuenta SQL de mínimo privilegio.
9. Rate limiting también en el proxy.
10. Monitoreo de 401, 403, 429, 5xx y consumo de Foundry.

Si un proxy termina TLS localmente, debe entregar correctamente el esquema y
host originales. Configura con cuidado qué IPs tienen permitido enviar headers
proxy; de lo contrario un cliente podría falsificarlos.

## Limitaciones pendientes

- Las lecturas del panel no tienen identidad ni autorización por usuario.
- `NINFAS_ADMIN_API_KEY` es una clave compartida, no una sesión revocable.
- El rate limiter es local al proceso.
- No hay registro específico de quién administró un ave.
- No hay protección distribuida contra abuso ni WAF.
- TLS pertenece a la infraestructura externa.
- Los errores detallados se escriben en salida/log local; hay que protegerlos.
- La seguridad del dispositivo de cámara y sus credenciales queda fuera del
  proceso Python.

Antes de exponer el proyecto públicamente conviene implementar un proveedor de
identidad, roles, auditoría, secretos administrados y pruebas de penetración.
