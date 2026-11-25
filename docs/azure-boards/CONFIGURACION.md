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

El Kanban **Stories** se verificó en la interfaz tras la configuración y el cierre: la columna **Closed** contiene las historias **#31, #32 y #33**, con las columnas **New, Active, Resolved y Closed** activas y sin errores de mapeo tras la migración a Agile (`Active` y `Resolved` quedaron en `0 / 5`).

## Backlog creado

`backlog.json` registra 1 Epic, 8 Features y 24 User Stories con criterios, fuentes y prioridades. Cada elemento incluye su `azureId` y `azureUrl`; las claves EPIC01, F01 y US01 siguen siendo identificadores locales. El Epic tiene ID 1 y las Features tienen IDs 2, 6, 10, 14, 18, 22, 26 y 30. Las historias ocupan los restantes IDs hasta el 33.

`New` fue el estado inicial. Las tres historias de la [Feature #30](https://dev.azure.com/matiisnothere/NinfasProyecto/_workitems/edit/30) (**#31, #32 y #33**) y la propia Feature **#30** quedaron en estado **Closed** (`Acceptance tests pass`), con evidencia registrada en Discussion: #31 cerrada tras configurar el tablero y el backlog; #32 y #33 cerradas automáticamente por `Microsoft.VisualStudio.Services.TFS` al integrarse el [PR #2](https://github.com/matiisnothere-15/CamaraNinfa/pull/2) en `main` mediante `Closed AB#32` y `Closed AB#33`; y la Feature #30 cerrada tras verificar sus tres historias hijas en `Closed`. Las demás historias (F01–F07, #2–#29) conservan su trabajo pendiente. La creación del backlog no demuestra el cumplimiento funcional de las historias pendientes. No se inventaron responsables ni estimaciones iniciales (los elementos #32 y #33 quedaron asignados a Matias Riquelme en la interfaz).

## Integración y pruebas automáticas

El usuario solicitó **GitHub conectado a Boards y pruebas automáticas** y completó ambas autorizaciones. Azure confirma la conexión **matiisnothere-15**, de tipo **GitHub App**, limitada a **matiisnothere-15/CamaraNinfa**. GitHub aloja el código; no se solicitó un espejo en Azure Repos. [Documentación de integración de Microsoft](https://learn.microsoft.com/en-us/azure/devops/boards/github/?view=azure-devops).

**Los enlaces `AB#ID` y el cierre automático están verificados**: Development de las historias #32 y #33 muestra el [PR #1](https://github.com/matiisnothere-15/CamaraNinfa/pull/1) (`581401f965b46aef9da9a19e3b669b4e6713492d`), el [PR #2](https://github.com/matiisnothere-15/CamaraNinfa/pull/2) (`38b063db05bd157eded9d0c038a2ed30155e3c20`), los commits asociados y `Integrated in build CamaraNinfa CI_20261119.4` (`Succeeded`). Al fusionarse el PR #2 con `Closed AB#32` y `Closed AB#33` en la descripción, Azure Boards transicionó automáticamente ambas historias a **Closed** (`Acceptance tests pass`).

Para enlazar los próximos cambios automáticamente, el usuario debe incluir **`AB#ID` en el mensaje de commit o en la descripción del PR**, sustituyendo ID por el número real de la historia. Una referencia aislada enlaza el cambio sin cerrar la historia. Para el flujo de cierre al integrar en `main`, usar **`Closed AB#ID` en la descripción del PR destinado a `main`** y comprobar el cierre después del merge. Poner la referencia solo en el título del PR o en un comentario no crea el enlace de Development. [Sintaxis y condiciones oficiales](https://learn.microsoft.com/en-us/azure/devops/boards/github/link-to-from-github?view=azure-devops).

La autorización OAuth se completó y la app **AzurePipelines** quedó instalada (Service Connection `matiisnothere-15`). El pipeline **CamaraNinfa CI** (`definitionId=1`) está creado en Azure con `azure-pipelines.yml` (`Automatically link work items` habilitado para `main`). Historial de ejecuciones comprobadas:

- **Builds [1](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=1) (`#20261119.1`, `codex/azure-boards-ci`) y [2](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=2) (`#20261119.2`, `main` `581401f`)**: **Failed** (`134 passed, 2 failed, 3 skipped`) porque el checkout en `windows-latest` convirtió `entrenamiento/data.yaml` a CRLF y faltaba `.env.example` (Ruff, verificador y auditoría pasaron).
- **Build [3](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=3) (`#20261119.3`, Pull Request #2, commit `1cd4790`)**: **Succeeded** en `3m 7s` (`Pull request`), con Ruff, `verificar_proyecto.py`, `auditar_dataset.py` y **140 pruebas aprobadas, 0 fallidas, 0 omitidas (100%)**.
- **Build [4](https://dev.azure.com/matiisnothere/NinfasProyecto/_build/results?buildId=4) (`#20261119.4`, push a `main`, commit `38b063d`)**: **Succeeded** en `3m 6s` (`Individual CI`), con Ruff, `verificar_proyecto.py`, `auditar_dataset.py` y **140 pruebas aprobadas, 0 fallidas, 0 omitidas (100%)**.

Validación local ejecutada el 19 de noviembre de 2026: **140 pruebas aprobadas, 0 omitidas y Ruff sin observaciones**. Esto verifica la suite actual y no sustituye las pruebas con cámara, Azure SQL o Foundry reales. La organización muestra capacidad Microsoft-hosted de un trabajo y 1800 minutos mensuales.

## CSV de carga inicial

**IMPORTANTE: CSV sin IDs es solo importación inicial; volver a importar crea duplicados.**

`importar-sprint-actual.csv` se conserva como evidencia de la carga inicial de 33 elementos. No debe reutilizarse para actualizar el backlog ya creado. Para cambios posteriores, usar los IDs reales o exportar los elementos existentes y seguir el flujo de actualización. [Guía oficial de CSV](https://learn.microsoft.com/en-us/azure/devops/boards/queries/import-work-items-from-csv?view=azure-devops).

## Evidencia y límites

Las etiquetas `codigo-existente` señalan implementación localizada, sin afirmar que funciona hoy con cámara, SQL o Foundry reales. Las historias de integración permanecen pendientes hasta registrar evidencia.

La base del backlog importado y sus enlaces de fuentes permanece fijada al HEAD `2301f356bcaa6000c4beee61c6b29abe1f150c2a` y la documentación autorizada por el usuario. Desde esa base se corrigió el fallo de rotación de capturas en el [PR #1](https://github.com/matiisnothere-15/CamaraNinfa/pull/1) (`581401f`), y en el [PR #2](https://github.com/matiisnothere-15/CamaraNinfa/pull/2) (`38b063d`) se corrigió la lectura de saltos de línea en `entrenamiento/data.yaml` (`.gitattributes` + `modulos/dataset_audit.py`), se restauró `.env.example` sin secretos y se actualizó la documentación de RF-DETR; estos cambios no reescriben las fuentes históricas del backlog. La entrega de julio describe YOLO; el HEAD selecciona RF-DETR por defecto y sus dependencias opcionales quedan documentadas en `README.md` y `docs/CONFIGURACION_Y_OPERACION.md` (las métricas YOLO siguen sin validar RF-DETR). Los secretos reales no deben incorporarse al backlog ni a `.env.example`.

El despliegue público y recursos de pago no forman parte de esta configuración. Los archivos locales se validaron como JSON/CSV UTF-8, con jerarquía, conteos y fuentes existentes; la validación funcional del producto exige las pruebas e integraciones indicadas en cada historia.
