# Configuración de Azure Boards — NinfasProyecto

Estado comprobado el 19 de noviembre de 2026: **33 elementos creados y guardados en Azure Boards**. La interfaz confirmó `Successfully saved 33 work items` y el árbol mostró los tres niveles Epic, Feature y User Story.

Proyecto: [NinfasProyecto](https://dev.azure.com/matiisnothere/NinfasProyecto/). Código: [CamaraNinfa](https://github.com/matiisnothere-15/CamaraNinfa). Epic: [Monitor de Ninfas](https://dev.azure.com/matiisnothere/NinfasProyecto/_workitems/edit/1).

## Configuración aplicada

- Proceso **Agile**, con confirmación de cambio desde Basic.
- Equipo **NinfasProyecto Team**, Epics habilitados y Bugs tratados como requisitos.
- Área **NinfasProyecto**.
- Iteración **NinfasProyecto\Sprint 1**, del **16 al 29 de noviembre de 2026**.
- Iteración predeterminada del equipo: `@CurrentIteration`.
- Los 33 elementos quedaron bajo el área y la iteración indicadas.

El Kanban **Stories** se verificó en la interfaz: las historias creadas aparecen en **New**, con las columnas **New, Active, Resolved y Closed** disponibles. No se observó error de mapeo de columnas después de la migración a Agile.

## Backlog creado

`backlog.json` registra 1 Epic, 8 Features y 24 User Stories con criterios, fuentes y prioridades. Cada elemento incluye su `azureId` y `azureUrl`; las claves EPIC01, F01 y US01 siguen siendo identificadores locales. El Epic tiene ID 1 y las Features tienen IDs 2, 6, 10, 14, 18, 22, 26 y 30. Las historias ocupan los restantes IDs hasta el 33.

`New` fue el estado inicial. La historia #31 está **Closed**, con evidencia en Discussion. Las historias #32 y #33 están **Active**, con comentarios y enlaces del PR #1 verificados; el cierre automático y la ejecución verde de CI se validan en el PR #2. Las demás historias conservan su trabajo pendiente. La creación del backlog no demuestra el cumplimiento de las historias. No se inventaron responsables ni estimaciones.

## Integración y pruebas automáticas

El usuario solicitó **GitHub conectado a Boards y pruebas automáticas** y completó ambas autorizaciones. Azure confirma la conexión **matiisnothere-15**, de tipo **GitHub App**, limitada a **matiisnothere-15/CamaraNinfa**. GitHub aloja el código; no se solicitó un espejo en Azure Repos. [Documentación de integración de Microsoft](https://learn.microsoft.com/en-us/azure/devops/boards/github/?view=azure-devops).

**El enlace `AB#32` está verificado**: Development de la historia #32 muestra el [PR #1](https://github.com/matiisnothere-15/CamaraNinfa/pull/1) (integrado en `main` en el commit `581401f965b46aef9da9a19e3b669b4e6713492d`) junto con los commits asociados.

Para enlazar los próximos cambios automáticamente, el usuario debe incluir **`AB#ID` en el mensaje de commit o en la descripción del PR**, sustituyendo ID por el número real de la historia. Una referencia aislada enlaza el cambio sin cerrar la historia. Para el flujo de cierre al integrar en `main`, usar **`Closed AB#ID` en la descripción del PR destinado a `main`** y comprobar el cierre después del merge. Poner la referencia solo en el título del PR o en un comentario no crea el enlace de Development. [Sintaxis y condiciones oficiales](https://learn.microsoft.com/en-us/azure/devops/boards/github/link-to-from-github?view=azure-devops).

La autorización OAuth se completó y la app **AzurePipelines** quedó instalada (Service Connection `matiisnothere-15`). El pipeline **CamaraNinfa CI** (`definitionId=1`) está creado en Azure con `azure-pipelines.yml`. Sus dos primeras ejecuciones reales ([build 1](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=1) sobre `codex/azure-boards-ci` y [build 2](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=2) tras el merge del PR #1 en `main`, commit `581401f`) fallaron en 2 pruebas de huella del dataset (`134 passed, 2 failed, 3 skipped`) porque el checkout en `windows-latest` convirtió `entrenamiento/data.yaml` a CRLF y faltaba `.env.example`. En la rama `fix/ci-dataset-eol-y-docs` (PR #2) se agrega `.gitattributes`, se normalizan los saltos de línea al leer `data.yaml` en `modulos/dataset_audit.py`, se restaura `.env.example` sin secretos y se actualiza la documentación de RF-DETR en `README.md` y `docs/CONFIGURACION_Y_OPERACION.md`.

Validación local ejecutada el 19 de noviembre de 2026: **140 pruebas aprobadas, 0 omitidas y Ruff sin observaciones**. Esto verifica la suite actual y no sustituye las pruebas con cámara, Azure SQL o Foundry reales.

La organización muestra capacidad Microsoft-hosted de un trabajo y 1800 minutos mensuales. El resultado verde remoto sobre PR #2 y `main`, junto con el cierre verificado de #32, #33 y la Feature #30, se registrarán al completar el merge del PR #2.

## CSV de carga inicial

**IMPORTANTE: CSV sin IDs es solo importación inicial; volver a importar crea duplicados.**

`importar-sprint-actual.csv` se conserva como evidencia de la carga inicial de 33 elementos. No debe reutilizarse para actualizar el backlog ya creado. Para cambios posteriores, usar los IDs reales o exportar los elementos existentes y seguir el flujo de actualización. [Guía oficial de CSV](https://learn.microsoft.com/en-us/azure/devops/boards/queries/import-work-items-from-csv?view=azure-devops).

## Evidencia y límites

Las etiquetas `codigo-existente` señalan implementación localizada, sin afirmar que funciona hoy con cámara, SQL o Foundry reales. Las historias de integración permanecen pendientes hasta registrar evidencia.

La base del backlog importado y sus enlaces de fuentes permanece fijada al HEAD `2301f356bcaa6000c4beee61c6b29abe1f150c2a` y la documentación autorizada por el usuario. Desde esa base se corrigió el fallo de rotación de capturas en el PR #1, y en la rama `fix/ci-dataset-eol-y-docs` (PR #2) se corrigió la lectura de saltos de línea en `entrenamiento/data.yaml`, se restauró `.env.example` sin secretos y se actualizó la documentación de RF-DETR; estos cambios no reescriben las fuentes históricas del backlog. La entrega de julio describe YOLO; el HEAD selecciona RF-DETR por defecto y sus dependencias opcionales quedan documentadas en `README.md` y `docs/CONFIGURACION_Y_OPERACION.md` (las métricas YOLO siguen sin validar RF-DETR). Los secretos reales no deben incorporarse al backlog ni a `.env.example`.

El despliegue público y recursos de pago no forman parte de esta configuración. Los archivos locales se validaron como JSON/CSV UTF-8, con jerarquía, conteos y fuentes existentes; la validación funcional del producto exige las pruebas e integraciones indicadas en cada historia.

Las actualizaciones finales de `backlog.json` y este documento se completarán cuando se registre el resultado verde del PR #2 y de `main`.
