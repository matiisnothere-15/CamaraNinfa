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

`New` fue el estado inicial. La historia #31 se verifico y se cerro en la interfaz, con evidencia en Discussion; las demas historias conservan su trabajo pendiente. La creación del backlog no demuestra el cumplimiento de las historias. No se inventaron responsables ni estimaciones.

## Integración y pruebas automáticas

El usuario solicitó **GitHub conectado a Boards y pruebas automáticas**. La conexion con GitHub y el pipeline siguen **pendientes de autorizacion del usuario en GitHub y de verificacion remota**. Las pantallas de instalacion de Azure Boards y autorizacion OAuth de Azure Pipelines estan abiertas en el navegador integrado. GitHub aloja el código; no se solicitó un espejo en Azure Repos.

La integración debe conectar el repositorio correcto y comprobar sus enlaces de desarrollo. [Documentación de integración de Microsoft](https://learn.microsoft.com/en-us/azure/devops/boards/github/?view=azure-devops).

Una referencia como `AB#32` en el mensaje de commit o la descripción del PR permite enlazar la historia de integración. La referencia aislada no cambia su estado; las transiciones dependen del texto y del flujo configurado. Verificar el resultado en Development antes de dar la conexión por probada. [Sintaxis y condiciones oficiales](https://learn.microsoft.com/en-us/azure/devops/boards/github/link-to-from-github?view=azure-devops).

El archivo `azure-pipelines.yml` está preparado para las pruebas automáticas solicitadas, pero **todavía no se ha ejecutado en Azure Pipelines**. La comprobación remota debe confirmar los disparadores de push y pull request y conservar una ejecución real verificable.

Validación local ejecutada el 19 de noviembre de 2026: **139 pruebas aprobadas y Ruff sin observaciones**. Esto verifica la suite actual y no sustituye las pruebas con cámara, Azure SQL o Foundry reales.

Los cambios estan publicados en la rama [codex/azure-boards-ci](https://github.com/matiisnothere-15/CamaraNinfa/tree/codex/azure-boards-ci) y propuestos en el [PR #1](https://github.com/matiisnothere-15/CamaraNinfa/pull/1), pendiente de integracion. La prueba de diagnostico ODBC utiliza resultados controlados para comprobar tanto la disponibilidad como la ausencia del driver, sin depender del controlador instalado en el agente. La organizacion muestra capacidad Microsoft-hosted de un trabajo y 1800 minutos mensuales; la ejecucion remota todavia no esta verificada.

## CSV de carga inicial

**IMPORTANTE: CSV sin IDs es solo importación inicial; volver a importar crea duplicados.**

`importar-sprint-actual.csv` se conserva como evidencia de la carga inicial de 33 elementos. No debe reutilizarse para actualizar el backlog ya creado. Para cambios posteriores, usar los IDs reales o exportar los elementos existentes y seguir el flujo de actualización. [Guía oficial de CSV](https://learn.microsoft.com/en-us/azure/devops/boards/queries/import-work-items-from-csv?view=azure-devops).

## Evidencia y límites

Las etiquetas `codigo-existente` señalan implementación localizada, sin afirmar que funciona hoy con cámara, SQL o Foundry reales. Las historias de integración permanecen pendientes hasta registrar evidencia.

La base del backlog importado y sus enlaces de fuentes permanece fijada al HEAD `2301f356bcaa6000c4beee61c6b29abe1f150c2a` y la documentación autorizada por el usuario. Desde esa base se corrigió un fallo puntual de captura; el cambio no reescribe las fuentes históricas del backlog. La entrega de julio describe YOLO; ese HEAD selecciona RF-DETR por defecto. Sus dependencias opcionales requieren instrucciones reproducibles y las métricas YOLO no validan RF-DETR. `LICENSE` ya existe; `.env.example` se eliminó en ese HEAD aunque las guías aún exigen copiarlo. Los secretos reales no deben incorporarse al backlog.

El despliegue público y recursos de pago no forman parte de esta configuración. Los archivos locales se validaron como JSON/CSV UTF-8, con jerarquía, conteos y fuentes existentes; la validación funcional del producto exige las pruebas e integraciones indicadas en cada historia.
