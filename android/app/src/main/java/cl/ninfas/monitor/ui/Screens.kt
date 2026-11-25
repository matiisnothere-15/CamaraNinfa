package cl.ninfas.monitor.ui

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import cl.ninfas.monitor.data.ActionEvent
import cl.ninfas.monitor.data.Bird
import cl.ninfas.monitor.data.Metric
import cl.ninfas.monitor.data.Recommendation
import cl.ninfas.monitor.data.Snapshot
import java.util.Locale

@Composable
internal fun HomeScreen(
    state: NinfasUiState,
    onRecordVisit: (String, String?, Double?) -> Unit = { _, _, _ -> },
) {
    val snapshot = state.snapshot
    val allActions = remember(state.capturedActions, snapshot?.actions) {
        combineActions(state.capturedActions, snapshot?.actions.orEmpty())
    }
    val latestAction = allActions.firstOrNull()
    var recordOpen by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().background(IvoryBackground).testTag("home_list"),
            contentPadding = PaddingValues(start = NinfasSpacing.screenPadding, top = NinfasSpacing.screenPadding, end = NinfasSpacing.screenPadding, bottom = 36.dp),
            verticalArrangement = Arrangement.spacedBy(NinfasSpacing.lg),
        ) {
        item {
            LastObservationCard(
                latestAction = latestAction,
                snapshot = snapshot,
                birdPhotos = state.birdPhotos,
                onOpenRecord = { recordOpen = true },
            )
        }

        if (snapshot == null) {
            item { NoSnapshot(state) }
        } else {
            item {
                val health = snapshot.health
                val current = state.error == null && monitorIsCurrent(
                    health.status,
                    health.databaseAvailable,
                    health.monitorActive,
                    health.lastSnapshot,
                    state.now,
                )
                Surface(
                    color = if (current) PureWhite else ClayContainer,
                    border = BorderStroke(1.dp, if (current) WarmOutline else ClayError.copy(alpha = 0.45f)),
                    shape = MaterialTheme.shapes.large,
                ) {
                    Column(
                        Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.sm),
                        ) {
                            Icon(
                                imageVector = if (current) Icons.Outlined.CheckCircle else Icons.Outlined.WarningAmber,
                                contentDescription = null,
                                tint = if (current) ForestGreen else ClayError,
                            )
                            Text(
                                text = if (current) "Monitor activo"
                                else if (state.error != null) "Conexión sin actualizar"
                                else "Monitor sin reporte actual",
                                style = MaterialTheme.typography.titleMedium,
                                color = if (current) InkText else ClayError,
                            )
                        }
                        Text(
                            "Último reporte: ${localReportTime(health.lastSnapshot)}",
                            style = tabularStyle(MaterialTheme.typography.bodyMedium),
                            color = InkText,
                        )
                        if (!current) {
                            Text(
                                when {
                                    !health.databaseAvailable -> "La base de datos no está disponible. Revisa la conexión del servidor."
                                    !health.monitorActive -> "El monitor no está activo. Revisa la PC y vuelve a actualizar."
                                    health.status != "ok" -> "El servidor informa un estado degradado."
                                    else -> "El reporte está ausente o es antiguo. Verifica el monitor en la PC."
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = ClayError,
                            )
                        }
                        if (health.pendingBatches > 0) {
                            Text(
                                "${health.pendingBatches} lotes pendientes de guardar",
                                style = MaterialTheme.typography.bodySmall,
                                color = SlateSecondary,
                            )
                        }
                        Text(
                            "Consultado: ${localReportTime(snapshot.fetchedAt.toString())}",
                            style = tabularStyle(MaterialTheme.typography.labelSmall),
                            color = SlateSecondary,
                        )
                    }
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.xs)) {
                    Text("Cómo está la jaula", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Ánimo, actividad y audio describen a la jaula completa.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = SlateSecondary,
                    )
                }
            }

            if (snapshot.metrics.isEmpty()) {
                item {
                    EmptyState(
                        "Aún no hay métricas",
                        "La PC mostrará datos cuando el monitor registre observaciones.",
                    )
                }
            } else {
                item {
                    Surface(
                        color = PureWhite,
                        shape = MaterialTheme.shapes.large,
                        border = BorderStroke(1.dp, WarmOutline),
                    ) {
                        Column(Modifier.fillMaxWidth()) {
                            FieldMetricRow("Ánimo", snapshot.metrics["EstadoAnimo"])
                            HorizontalDivider(color = WarmOutline)
                            FieldMetricRow("Actividad", snapshot.metrics["Actividad"], activity = true)
                            HorizontalDivider(color = WarmOutline)
                            FieldMetricRow("Audio", snapshot.metrics["Audio"])
                            HorizontalDivider(color = WarmOutline)
                            FieldMetricRow("Sin visita al comedero", snapshot.metrics["SinComer"], hours = true)
                            HorizontalDivider(color = WarmOutline)
                            FieldMetricRow("Sin visita al bebedero", snapshot.metrics["SinBeber"], hours = true)
                        }
                    }
                }
                item {
                    Text(
                        "Las visitas observadas no confirman cuánto comieron o bebieron.",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateSecondary,
                    )
                }
            }

            item {
                Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.xs)) {
                    Text("Para tener presente", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "Recomendaciones de las últimas 24 horas",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateSecondary,
                    )
                    if (!currentHealth(snapshot.health, state.now) || state.error != null) {
                        Text(
                            "Pueden basarse en reportes antiguos. Verifica el monitor antes de interpretarlas.",
                            style = MaterialTheme.typography.bodySmall,
                            color = ClayError,
                        )
                    }
                }
            }

            if (snapshot.recommendations.isEmpty()) {
                item {
                    EmptyState("Sin recomendaciones", "No hay recomendaciones para este período.")
                }
            }
            items(snapshot.recommendations) { RecommendationRow(it) }
        }
    }

        if (recordOpen) {
            RecordVisitOverlay(
                birds = snapshot?.birds.orEmpty(),
                onDismiss = { recordOpen = false },
                onSave = { action, birdName, duration ->
                    onRecordVisit(action, birdName, duration)
                    recordOpen = false
                },
            )
        }
    }
}

@Composable
private fun LastObservationCard(
    latestAction: ActionEvent?,
    snapshot: Snapshot?,
    birdPhotos: Map<Int, String>,
    onOpenRecord: () -> Unit,
) {
    Surface(
        color = PureWhite,
        shape = MaterialTheme.shapes.large,
        border = BorderStroke(1.dp, WarmOutline),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
            verticalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
        ) {
            when {
                latestAction != null -> {
                    val birdName = resolveEventBirdName(latestAction)
                    val matchedBird = birdName?.let { name ->
                        snapshot?.birds?.firstOrNull { it.name.equals(name, ignoreCase = true) }
                    }
                    val photoPath = matchedBird?.let { birdPhotos[it.id] }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.Top,
                        horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
                    ) {
                        if (birdName != null) {
                            BirdPortrait(
                                name = birdName,
                                photoPath = photoPath,
                                size = 56.dp,
                            )
                        } else {
                            Surface(
                                color = IvoryBackground,
                                shape = RoundedCornerShape(14.dp),
                                border = BorderStroke(1.dp, WarmOutline),
                                modifier = Modifier.size(56.dp),
                            ) {
                                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                    CockatielMark(Modifier.size(40.dp))
                                }
                            }
                        }
                        Column(
                            modifier = Modifier.weight(1f),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    "ÚLTIMA OBSERVACIÓN",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = SlateSecondary,
                                )
                                Text(
                                    localHourOnly(latestAction.date),
                                    style = tabularStyle(MaterialTheme.typography.titleMedium),
                                    color = SlateSecondary,
                                )
                            }
                            Text(
                                formatCaregiverEventTitle(latestAction),
                                style = MaterialTheme.typography.titleLarge,
                                color = InkText,
                            )
                            formatCaregiverDuration(latestAction)?.let { durationLine ->
                                Text(
                                    durationLine,
                                    style = tabularStyle(MaterialTheme.typography.bodySmall),
                                    color = SlateSecondary,
                                )
                            }
                        }
                    }
                }
                snapshot != null && snapshot.metrics.isNotEmpty() -> {
                    val moodState = snapshot.metrics["EstadoAnimo"]?.state?.replace("Comodo", "Cómodo") ?: "En calma"
                    val time = localHourOnly(snapshot.health.lastSnapshot)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
                    ) {
                        CockatielMark(Modifier.size(48.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("ÚLTIMA OBSERVACIÓN", style = MaterialTheme.typography.labelSmall, color = SlateSecondary)
                            Text(
                                "$moodState a las $time",
                                style = tabularStyle(MaterialTheme.typography.titleLarge),
                                color = InkText,
                            )
                            Text(
                                "Corresponde a la jaula completa",
                                style = MaterialTheme.typography.bodySmall,
                                color = SlateSecondary,
                            )
                        }
                    }
                }
                else -> {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
                    ) {
                        CockatielMark(Modifier.size(48.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text("ÚLTIMA OBSERVACIÓN", style = MaterialTheme.typography.labelSmall, color = SlateSecondary)
                            Text(
                                "Sin observaciones registradas",
                                style = MaterialTheme.typography.titleLarge,
                                color = InkText,
                            )
                            Text(
                                "Inicia el monitor de cámara en tu PC o registra una visita manualmente.",
                                style = MaterialTheme.typography.bodySmall,
                                color = SlateSecondary,
                            )
                        }
                    }
                }
            }
            Button(
                onClick = onOpenRecord,
                colors = ButtonDefaults.buttonColors(
                    containerColor = ForestGreen,
                    contentColor = PureWhite,
                ),
                modifier = Modifier.fillMaxWidth().testTag("home_record_visit_button"),
            ) {
                Icon(Icons.Outlined.EditNote, null, Modifier.size(18.dp))
                Spacer(Modifier.width(NinfasSpacing.sm))
                Text("Registrar visita")
            }
        }
    }
}

@Composable
internal fun BirdPortrait(
    name: String,
    photoPath: String?,
    modifier: Modifier = Modifier,
    size: Dp = 60.dp,
) {
    val bitmap: ImageBitmap? = remember(photoPath) {
        photoPath?.let { path ->
            runCatching { BitmapFactory.decodeFile(path)?.asImageBitmap() }.getOrNull()
        }
    }
    val shape = RoundedCornerShape(16.dp)
    if (bitmap != null) {
        Image(
            bitmap = bitmap,
            contentDescription = "Retrato de $name",
            contentScale = ContentScale.Crop,
            modifier = modifier
                .size(size)
                .clip(shape)
                .border(1.dp, WarmOutline, shape),
        )
    } else {
        Surface(
            color = SageFilter,
            shape = shape,
            border = BorderStroke(1.dp, ForestGreen.copy(alpha = 0.25f)),
            modifier = modifier.size(size),
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    text = birdInitial(name),
                    style = MaterialTheme.typography.headlineSmall.copy(fontFamily = SpeciesSerif),
                    color = ForestGreen,
                )
            }
        }
    }
}

@Composable
private fun FieldMetricRow(
    title: String,
    metric: Metric?,
    activity: Boolean = false,
    hours: Boolean = false,
) {
    val value = when {
        metric == null -> "Sin datos"
        hours -> "${number(metric.value)} h"
        else -> metric.state?.replace("Comodo", "Cómodo") ?: "Sin estado"
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = NinfasSpacing.lg, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = InkText)
            if (activity && metric != null) {
                Text(
                    "${number(metric.value)} % diagonal/min",
                    style = tabularStyle(MaterialTheme.typography.bodySmall),
                    color = SlateSecondary,
                )
            }
            if (hours && metric?.state != null) {
                Text(
                    metric.state,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (metric.state == "Alerta") ClayError else ForestGreen,
                )
            }
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                value,
                style = tabularStyle(MaterialTheme.typography.titleMedium),
                color = InkText,
                textAlign = TextAlign.End,
            )
            Text(
                if (metric == null) "Sin observaciones" else localReportTime(metric.date),
                style = tabularStyle(MaterialTheme.typography.labelSmall),
                color = SlateSecondary,
                textAlign = TextAlign.End,
            )
        }
    }
}

@Composable
private fun RecommendationRow(recommendation: Recommendation) {
    val urgent = recommendation.level == "urgente"
    val attention = recommendation.level == "atencion"
    val label = when (recommendation.level) {
        "urgente" -> "Urgente"
        "atencion" -> "Atención"
        "bien" -> "Bien"
        else -> "Información"
    }
    val tint = when {
        urgent -> ClayError
        attention -> Color(0xFF8B5E08)
        else -> ForestGreen
    }
    Surface(
        color = PureWhite,
        shape = MaterialTheme.shapes.medium,
        border = BorderStroke(1.dp, if (urgent) ClayError.copy(alpha = 0.4f) else WarmOutline),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
            horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
        ) {
            Icon(
                if (urgent || attention) Icons.Outlined.WarningAmber else Icons.Outlined.Info,
                contentDescription = null,
                tint = tint,
            )
            Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.xs)) {
                Text(label, style = MaterialTheme.typography.labelMedium, color = tint)
                Text(recommendation.title, style = MaterialTheme.typography.titleMedium, color = InkText)
                Text(recommendation.detail, style = MaterialTheme.typography.bodyMedium, color = SlateSecondary)
            }
        }
    }
}

@Composable
internal fun HistoryScreen(
    state: NinfasUiState,
    selectHours: (Int) -> Unit,
    onRecordVisit: (String, String?, Double?) -> Unit = { _, _, _ -> },
) {
    val snapshot = state.snapshot
    val allActions = remember(state.capturedActions, snapshot?.actions) {
        combineActions(state.capturedActions, snapshot?.actions.orEmpty())
    }
    val groupedDays = remember(allActions, state.now) {
        groupActionsByDay(allActions, state.now)
    }
    var recordOpen by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().background(IvoryBackground).testTag("history_list"),
            contentPadding = PaddingValues(start = NinfasSpacing.screenPadding, top = NinfasSpacing.screenPadding, end = NinfasSpacing.screenPadding, bottom = 36.dp),
            verticalArrangement = Arrangement.spacedBy(NinfasSpacing.lg),
        ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.md)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.sm),
                ) {
                    Text(
                        "Historial de la jaula",
                        style = MaterialTheme.typography.headlineSmall,
                        modifier = Modifier.weight(1f),
                    )
                    Button(
                        onClick = { recordOpen = true },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = ForestGreen,
                            contentColor = PureWhite,
                        ),
                        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
                        modifier = Modifier.testTag("history_record_visit_button"),
                    ) {
                        Icon(Icons.Outlined.EditNote, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Registrar visita", maxLines = 1)
                    }
                }
                RangeSelector(state.hours, selectHours)
            }
        }

        if (snapshot == null && allActions.isEmpty()) {
            item { NoSnapshot(state) }
        } else {
            if (snapshot != null) {
                item { HistoryChart("Estado de ánimo", snapshot.history.filter { it.metric == "EstadoAnimo" }, mood = true) }
                item { HistoryChart("Actividad", snapshot.history.filter { it.metric == "Actividad" }, mood = false) }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.xs)) {
                    Text("Eventos observados", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "${allActions.size} eventos · ${rangeLabel(state.hours)}",
                        style = tabularStyle(MaterialTheme.typography.bodySmall),
                        color = SlateSecondary,
                    )
                    Text(
                        "Una visita no confirma cuánto comieron o bebieron. Cuando no se distingue la ninfa, se muestra sin atribuir.",
                        style = MaterialTheme.typography.bodySmall,
                        color = SlateSecondary,
                    )
                }
            }
            if (groupedDays.isEmpty()) {
                item {
                    EmptyState(
                        "Sin eventos en este rango",
                        "Cambia el rango o registra una visita para conservarla en este historial.",
                    )
                }
            } else {
                items(groupedDays, key = { it.first }) { (dayTitle, dayEvents) ->
                    DayEventsGroup(dayTitle = dayTitle, events = dayEvents)
                }
            }
        }
    }

        if (recordOpen) {
            RecordVisitOverlay(
                birds = snapshot?.birds.orEmpty(),
                onDismiss = { recordOpen = false },
                onSave = { action, birdName, duration ->
                    onRecordVisit(action, birdName, duration)
                    recordOpen = false
                },
            )
        }
    }
}

@Composable
internal fun RangeSelector(hours: Int, select: (Int) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.sm)) {
        listOf(6, 24, 168).forEach { value ->
            val selected = hours == value
            FilterChip(
                selected = selected,
                onClick = { select(value) },
                label = { Text(rangeLabel(value)) },
                leadingIcon = if (selected) {
                    {
                        Icon(
                            imageVector = Icons.Outlined.Check,
                            contentDescription = "Seleccionado",
                            modifier = Modifier.size(16.dp),
                        )
                    }
                } else null,
                colors = FilterChipDefaults.filterChipColors(
                    containerColor = PureWhite,
                    labelColor = SlateSecondary,
                    selectedContainerColor = SageFilter,
                    selectedLabelColor = ForestGreen,
                    selectedLeadingIconColor = ForestGreen,
                ),
                border = FilterChipDefaults.filterChipBorder(
                    enabled = true,
                    selected = selected,
                    borderColor = WarmOutline,
                    selectedBorderColor = ForestGreen.copy(alpha = 0.35f),
                ),
            )
        }
    }
}

@Composable
private fun DayEventsGroup(dayTitle: String, events: List<ActionEvent>) {
    Column(verticalArrangement = Arrangement.spacedBy(NinfasSpacing.sm)) {
        Text(
            text = dayTitle,
            style = MaterialTheme.typography.titleMedium.copy(fontFamily = SpeciesSerif),
            color = InkText,
        )
        Surface(
            color = PureWhite,
            shape = MaterialTheme.shapes.large,
            border = BorderStroke(1.dp, WarmOutline),
        ) {
            Column(Modifier.fillMaxWidth()) {
                events.forEachIndexed { index, action ->
                    ActionRow(action)
                    if (index < events.lastIndex) {
                        HorizontalDivider(color = WarmOutline)
                    }
                }
            }
        }
    }
}

@Composable
private fun ActionRow(action: ActionEvent) {
    val headline = formatCaregiverEventTitle(action)
    val durationLine = formatCaregiverDuration(action)
    val cleanNote = sanitizeLegacyNotes(action.notes)
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = NinfasSpacing.lg, vertical = 14.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Column(
            modifier = Modifier.weight(1f),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(headline, style = MaterialTheme.typography.titleMedium, color = InkText)
            durationLine?.let {
                Text(it, style = tabularStyle(MaterialTheme.typography.bodySmall), color = SlateSecondary)
            }
            cleanNote?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = SlateSecondary)
            }
        }
        Spacer(Modifier.width(NinfasSpacing.md))
        Text(
            text = localHourOnly(action.date),
            style = tabularStyle(MaterialTheme.typography.titleMedium),
            color = SlateSecondary,
            textAlign = TextAlign.End,
            modifier = Modifier.testTag("history_event_time"),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun BirdsScreen(state: NinfasUiState, model: NinfasViewModel) {
    var addOpen by remember(state.connection.baseUrl) { mutableStateOf(false) }
    var deleteTarget by remember(state.connection.baseUrl) { mutableStateOf<Bird?>(null) }
    var pendingPhotoBirdId by remember { mutableStateOf<Int?>(null) }

    val galleryLauncher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        val birdId = pendingPhotoBirdId
        pendingPhotoBirdId = null
        if (birdId != null) {
            model.assignBirdPhoto(birdId, uri)
        }
    }

    LaunchedEffect(state.mutationMessage, state.writing) {
        if (!state.writing && state.mutationMessage != null && !state.mutationError) addOpen = false
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(IvoryBackground).testTag("birds_list"),
        contentPadding = PaddingValues(start = NinfasSpacing.screenPadding, top = NinfasSpacing.screenPadding, end = NinfasSpacing.screenPadding, bottom = 36.dp),
        verticalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Mis ninfas",
                    style = MaterialTheme.typography.headlineSmall,
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { model.dismissMutationMessage(); addOpen = true },
                    enabled = !state.writing && state.connection.adminKey.isNotBlank(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = ForestGreen,
                        contentColor = PureWhite,
                    ),
                ) {
                    Icon(Icons.Outlined.Add, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Añadir")
                }
            }
            if (state.connection.adminKey.isBlank()) {
                Spacer(Modifier.height(NinfasSpacing.xs))
                Text(
                    "Añade la clave administrativa en Conexión para registrar o eliminar aves.",
                    style = MaterialTheme.typography.bodySmall,
                    color = SlateSecondary,
                )
            }
            Spacer(Modifier.height(NinfasSpacing.md))
            RangeSelector(state.hours, model::selectHours)
        }
        state.mutationMessage?.let { message -> item { Notice(message, state.mutationError) } }
        val snapshot = state.snapshot
        if (snapshot == null) {
            item { NoSnapshot(state) }
        } else {
            item {
                Text(
                    "Resumen por ave en ${rangeLabel(state.hours)}. Las visitas observadas no confirman ingesta.",
                    style = MaterialTheme.typography.bodySmall,
                    color = SlateSecondary,
                )
            }
            if (snapshot.birds.isEmpty()) {
                item {
                    EmptyState(
                        "Aún no hay ninfas registradas",
                        "Usa Añadir para crear el catálogo de tus aves.",
                    )
                }
            }
            items(snapshot.birds, key = { it.id }) { bird ->
                val stats = snapshot.stats.birds.firstOrNull { it.id == bird.id }
                val photoPath = state.birdPhotos[bird.id]
                val hasPhoto = !photoPath.isNullOrBlank()
                Surface(
                    color = PureWhite,
                    shape = MaterialTheme.shapes.large,
                    border = BorderStroke(1.dp, WarmOutline),
                ) {
                    Column(
                        Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
                        verticalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.md),
                        ) {
                            BirdPortrait(
                                name = bird.name,
                                photoPath = photoPath,
                                size = 60.dp,
                                modifier = Modifier.testTag("bird_portrait_${bird.id}"),
                            )
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(
                                    bird.name,
                                    style = MaterialTheme.typography.titleLarge.copy(fontFamily = SpeciesSerif),
                                    color = InkText,
                                )
                                Text(
                                    "Nymphicus hollandicus · Ninfa",
                                    style = MaterialTheme.typography.bodySmall.copy(
                                        fontFamily = SpeciesSerif,
                                        fontStyle = FontStyle.Italic,
                                    ),
                                    color = SlateSecondary,
                                )
                                bird.color?.takeIf { it.isNotBlank() }?.let {
                                    Text(it, style = MaterialTheme.typography.bodySmall, color = InkText)
                                }
                            }
                            IconButton(
                                onClick = { deleteTarget = bird },
                                enabled = !state.writing && state.connection.adminKey.isNotBlank(),
                            ) {
                                Icon(
                                    Icons.Outlined.DeleteOutline,
                                    "Eliminar a ${bird.name}",
                                    tint = SlateSecondary,
                                )
                            }
                        }

                        FlowRow(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                            itemVerticalAlignment = Alignment.CenterVertically,
                        ) {
                            OutlinedButton(
                                onClick = {
                                    pendingPhotoBirdId = bird.id
                                    galleryLauncher.launch("image/*")
                                },
                                border = BorderStroke(1.dp, ForestGreen.copy(alpha = 0.4f)),
                                colors = ButtonDefaults.outlinedButtonColors(
                                    containerColor = if (hasPhoto) PureWhite else SageFilter,
                                    contentColor = ForestGreen,
                                ),
                                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                                modifier = Modifier.testTag("bird_photo_button_${bird.id}"),
                            ) {
                                Icon(
                                    imageVector = if (hasPhoto) Icons.Outlined.PhotoLibrary else Icons.Outlined.AddAPhoto,
                                    contentDescription = null,
                                    modifier = Modifier.size(16.dp),
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(if (hasPhoto) "Cambiar foto" else "Añadir foto")
                            }
                            if (hasPhoto) {
                                OutlinedButton(
                                    onClick = { model.rotateBirdPhoto(bird.id) },
                                    border = BorderStroke(1.dp, WarmOutline),
                                    colors = ButtonDefaults.outlinedButtonColors(
                                        containerColor = PureWhite,
                                        contentColor = InkText,
                                    ),
                                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                                    modifier = Modifier.testTag("bird_rotate_photo_button_${bird.id}"),
                                ) {
                                    Icon(
                                        imageVector = Icons.Outlined.RotateRight,
                                        contentDescription = "Girar foto de ${bird.name}",
                                        modifier = Modifier.size(16.dp),
                                    )
                                    Spacer(Modifier.width(4.dp))
                                    Text("Girar")
                                }
                            }
                            bird.registered?.let {
                                Text(
                                    "Alta: ${localReportTime(it)}",
                                    style = tabularStyle(MaterialTheme.typography.labelSmall),
                                    color = SlateSecondary,
                                )
                            }
                        }

                        bird.notes?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall, color = SlateSecondary)
                        }

                        HorizontalDivider(color = WarmOutline)

                        if (stats == null) {
                            Text(
                                "Sin estadísticas individuales para este rango.",
                                style = MaterialTheme.typography.bodySmall,
                                color = SlateSecondary,
                            )
                        } else {
                            BirdStatLine("Comedero", stats.foodVisits, stats.foodSeconds, stats.lastFood)
                            BirdStatLine("Bebedero", stats.waterVisits, stats.waterSeconds, stats.lastWater)
                        }
                    }
                }
            }
            if (snapshot.stats.unidentified > 0) {
                item {
                    Notice("${snapshot.stats.unidentified} eventos sin identificar. Se muestran sin atribuir a ninguna ninfa.")
                }
            }
        }
    }
    if (addOpen) {
        AddBirdDialog(state, onDismiss = { if (!state.writing) addOpen = false }, onAdd = model::createBird)
    }
    deleteTarget?.let { bird ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            containerColor = PureWhite,
            title = { Text("¿Eliminar a ${bird.name}?", color = InkText) },
            text = { Text("Se eliminará esta ninfa del catálogo. Esta acción no se puede deshacer.", color = SlateSecondary) },
            confirmButton = {
                TextButton(
                    onClick = { model.deleteBird(bird.id); deleteTarget = null },
                    enabled = !state.writing,
                ) { Text("Eliminar a ${bird.name}", color = ClayError) }
            },
            dismissButton = {
                TextButton(onClick = { deleteTarget = null }) { Text("Cancelar", color = ForestGreen) }
            },
        )
    }
}

@Composable
private fun BirdStatLine(label: String, visits: Int, seconds: Double, last: String?) {
    val countText = formatVisitCount(visits)
    val timeText = if (visits == 0 && seconds <= 0.0) {
        "Sin tiempo observado"
    } else {
        "Tiempo observado: ${number(seconds)} s"
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(label, style = MaterialTheme.typography.titleSmall, color = InkText)
            Text(
                "$countText · $timeText",
                style = tabularStyle(MaterialTheme.typography.bodySmall),
                color = SlateSecondary,
            )
        }
        Text(
            text = if (last == null) "Sin visitas" else localReportTime(last),
            style = tabularStyle(MaterialTheme.typography.bodySmall),
            color = SlateSecondary,
            textAlign = TextAlign.End,
        )
    }
}

@Composable
private fun RecordVisitOverlay(
    birds: List<Bird>,
    onDismiss: () -> Unit,
    onSave: (String, String?, Double?) -> Unit,
) {
    BackHandler(onBack = onDismiss)
    var action by remember { mutableStateOf("Hidratacion") }
    var selectedBird by remember { mutableStateOf<String?>(birds.firstOrNull()?.name) }
    var durationInput by remember { mutableStateOf("") }
    val parsedDuration = durationInput.trim().replace(',', '.').toDoubleOrNull()
    val durationError = durationInput.isNotBlank() && (parsedDuration == null || parsedDuration <= 0.0)

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(InkText.copy(alpha = 0.48f))
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onDismiss,
            )
            .imePadding()
            .padding(NinfasSpacing.screenPadding),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            color = PureWhite,
            shape = MaterialTheme.shapes.large,
            border = BorderStroke(1.dp, WarmOutline),
            modifier = Modifier
                .fillMaxWidth()
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = {},
                ),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(NinfasSpacing.xl),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    "Registrar visita",
                    style = MaterialTheme.typography.titleLarge.copy(fontFamily = SpeciesSerif),
                    color = InkText,
                )
                Text("Lugar observado", style = MaterialTheme.typography.labelMedium, color = SlateSecondary)
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    listOf("Hidratacion" to "Bebedero", "Alimentacion" to "Comedero").forEach { (code, label) ->
                        val selected = action == code
                        FilterChip(
                            selected = selected,
                            onClick = { action = code },
                            label = { Text(label) },
                            leadingIcon = if (selected) {
                                { Icon(Icons.Outlined.Check, null, Modifier.size(16.dp)) }
                            } else null,
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = SageFilter,
                                selectedLabelColor = ForestGreen,
                                selectedLeadingIconColor = ForestGreen,
                            ),
                        )
                    }
                }
                Text("Ninfa", style = MaterialTheme.typography.labelMedium, color = SlateSecondary)
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    val options = listOf<String?>(null) + birds.map { it.name }
                    options.forEach { birdOption ->
                        val selected = selectedBird == birdOption
                        FilterChip(
                            selected = selected,
                            onClick = { selectedBird = birdOption },
                            label = { Text(birdOption ?: "Sin identificar") },
                            leadingIcon = if (selected) {
                                { Icon(Icons.Outlined.Check, null, Modifier.size(16.dp)) }
                            } else null,
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = SageFilter,
                                selectedLabelColor = ForestGreen,
                                selectedLeadingIconColor = ForestGreen,
                            ),
                        )
                    }
                }
                OutlinedTextField(
                    value = durationInput,
                    onValueChange = { durationInput = it },
                    label = { Text("Duración en segundos (opcional)") },
                    placeholder = { Text("Ej. 5,4") },
                    isError = durationError,
                    supportingText = if (durationError) {
                        { Text("Escribe un número mayor a 0", color = ClayError) }
                    } else null,
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextButton(onClick = onDismiss) { Text("Cancelar", color = SlateSecondary) }
                    Spacer(Modifier.width(8.dp))
                    Button(
                        onClick = { onSave(action, selectedBird, parsedDuration) },
                        enabled = !durationError,
                        colors = ButtonDefaults.buttonColors(containerColor = ForestGreen, contentColor = PureWhite),
                    ) {
                        Text("Guardar visita")
                    }
                }
            }
        }
    }
}

@Composable
private fun AddBirdDialog(state: NinfasUiState, onDismiss: () -> Unit, onAdd: (String, String, String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var color by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    val validation = birdInputError(name, color, notes)
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = PureWhite,
        title = { Text("Añadir ninfa", color = InkText, fontFamily = SpeciesSerif) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    name, { name = it },
                    label = { Text("Nombre") },
                    supportingText = { Text("${characterCount(name.trim())}/50") },
                    singleLine = true,
                    enabled = !state.writing,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                )
                OutlinedTextField(
                    color, { color = it },
                    label = { Text("Color (opcional)") },
                    supportingText = { Text("${characterCount(color)}/100") },
                    singleLine = true,
                    enabled = !state.writing,
                )
                OutlinedTextField(
                    notes, { notes = it },
                    label = { Text("Notas (opcional)") },
                    supportingText = { Text("${characterCount(notes)}/500") },
                    maxLines = 3,
                    enabled = !state.writing,
                )
                if (state.mutationError) state.mutationMessage?.let { Text(it, color = ClayError) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onAdd(name, color, notes) },
                enabled = validation == null && !state.writing,
            ) {
                if (state.writing) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = ForestGreen)
                else Text("Registrar ninfa", color = ForestGreen)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !state.writing) { Text("Cancelar", color = SlateSecondary) }
        },
    )
}

@Composable
internal fun AssistantScreen(state: NinfasUiState, ask: (String) -> Unit) {
    var question by remember(state.connection.baseUrl) { mutableStateOf("") }
    LazyColumn(
        modifier = Modifier.fillMaxSize().background(IvoryBackground).imePadding(),
        contentPadding = PaddingValues(start = NinfasSpacing.screenPadding, top = NinfasSpacing.screenPadding, end = NinfasSpacing.screenPadding, bottom = 36.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item {
            Text(
                "Consulta de cuaderno de campo",
                style = MaterialTheme.typography.headlineSmall.copy(fontFamily = SpeciesSerif),
                color = InkText,
            )
            Spacer(Modifier.height(NinfasSpacing.sm))
            Text(
                "Cada consulta es independiente y usa los reportes del monitor. No se guarda una conversación.",
                color = SlateSecondary,
            )
        }
        if (state.connection.adminKey.isBlank()) {
            item { Notice("Añade la clave administrativa en Conexión para usar el asistente.") }
        }
        item {
            OutlinedTextField(
                value = question,
                onValueChange = { question = it },
                label = { Text("Tu pregunta") },
                supportingText = { Text("${characterCount(question.trim())}/600 caracteres") },
                minLines = 4,
                maxLines = 8,
                isError = characterCount(question.trim()) > 600,
                enabled = !state.assistantBusy,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = PureWhite,
                    unfocusedContainerColor = PureWhite,
                    focusedBorderColor = ForestGreen,
                    unfocusedBorderColor = WarmOutline,
                    errorBorderColor = ClayError,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(NinfasSpacing.md))
            Button(
                onClick = { ask(question) },
                enabled = !state.assistantBusy &&
                    characterCount(question.trim()) in 1..600 &&
                    state.connection.adminKey.isNotBlank(),
                colors = ButtonDefaults.buttonColors(
                    containerColor = ForestGreen,
                    contentColor = PureWhite,
                ),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state.assistantBusy) {
                    CircularProgressIndicator(Modifier.size(18.dp), color = PureWhite, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.AutoMirrored.Outlined.Send, null, Modifier.size(18.dp))
                }
                Spacer(Modifier.width(NinfasSpacing.sm))
                Text(if (state.assistantBusy) "Consultando…" else "Consultar")
            }
        }
        state.assistantError?.let { message -> item { Notice(message, true) } }
        state.assistantReply?.let { reply ->
            item {
                Surface(
                    color = PureWhite,
                    shape = MaterialTheme.shapes.large,
                    border = BorderStroke(1.dp, WarmOutline),
                ) {
                    Column(
                        Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            "Respuesta",
                            style = MaterialTheme.typography.titleLarge.copy(fontFamily = SpeciesSerif),
                            color = InkText,
                        )
                        SelectionContainer {
                            Text(reply.answer, style = MaterialTheme.typography.bodyLarge, color = InkText)
                        }
                        if (reply.source.isNotBlank()) {
                            Text(
                                "Fuente: ${reply.source}",
                                style = MaterialTheme.typography.bodySmall,
                                color = SlateSecondary,
                            )
                        }
                    }
                }
            }
        }
        item {
            Text(
                "Si una consulta se interrumpe, no se reenvía automáticamente.",
                style = MaterialTheme.typography.bodySmall,
                color = SlateSecondary,
            )
        }
    }
}

@Composable
internal fun NoSnapshot(state: NinfasUiState) {
    if (state.loading) {
        Column(
            Modifier.fillMaxWidth().padding(vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(NinfasSpacing.lg),
        ) {
            CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 2.dp, color = ForestGreen)
            Text("Consultando los reportes…", color = SlateSecondary)
        }
    } else {
        EmptyState(
            "Sin reportes disponibles",
            if (state.error == null) "Actualiza para consultar el monitor de tu PC."
            else "Revisa la conexión y vuelve a actualizar.",
        )
    }
}

@Composable
internal fun EmptyState(title: String, detail: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = NinfasSpacing.lg), verticalArrangement = Arrangement.spacedBy(NinfasSpacing.sm)) {
        Text(title, style = MaterialTheme.typography.titleMedium, color = InkText)
        Text(detail, style = MaterialTheme.typography.bodyMedium, color = SlateSecondary)
    }
}

internal fun rangeLabel(hours: Int): String = if (hours == 168) "7 días" else "$hours h"
internal fun number(value: Double): String = if (value.isFinite()) String.format(Locale.forLanguageTag("es-CL"), "%.1f", value) else "Sin datos"
