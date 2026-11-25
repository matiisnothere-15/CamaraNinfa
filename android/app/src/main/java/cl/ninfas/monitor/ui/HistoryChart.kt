package cl.ninfas.monitor.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ChevronLeft
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import cl.ninfas.monitor.data.HistoryPoint
import java.time.Instant
import kotlin.math.abs
import kotlin.math.max

private data class PlotPoint(val instant: Instant, val value: Double, val state: String?)

private data class MoodSegment(
    val startMs: Long,
    val endMs: Long,
    val state: String?,
    val isGap: Boolean,
)

private data class ChartInspectionEntry(
    val startMs: Long,
    val endMs: Long,
    val title: String,
    val timeLabel: String,
    val subtitle: String?,
    val isGap: Boolean,
)

private val GapSand = Color(0xFFE7E1D3)

@Composable
internal fun HistoryChart(title: String, history: List<HistoryPoint>, mood: Boolean) {
    if (mood) {
        MoodTimelineChart(title = title, history = history)
    } else {
        ActivityLineChart(title = title, history = history)
    }
}

private fun normalizedMoodLabel(raw: String?): String = when (raw?.trim()) {
    "Comodo", "Cómodo" -> "Cómodo"
    "Normal" -> "Normal"
    "Estresado" -> "Estresado"
    "Desesperado" -> "Desesperado"
    else -> "Sin datos"
}

private fun moodColors(state: String?): Pair<Color, Color> = when (normalizedMoodLabel(state)) {
    "Cómodo" -> ForestGreen to PureWhite
    "Normal" -> SageFilter to InkText
    "Estresado" -> AmberTrigger to InkText
    "Desesperado" -> ClayError to PureWhite
    else -> GapSand to SlateSecondary
}

private fun detectGapThresholdMs(points: List<PlotPoint>): Long {
    if (points.size < 2) return 30 * 60_000L
    val deltas = (1 until points.size)
        .map { points[it].instant.toEpochMilli() - points[it - 1].instant.toEpochMilli() }
        .filter { it > 0L }
        .sorted()
    if (deltas.isEmpty()) return 30 * 60_000L
    val medianStepMs = deltas[deltas.size / 2]
    return (medianStepMs * 1.8).toLong().coerceIn(25 * 60_000L, 90 * 60_000L)
}

private fun buildMoodSegments(points: List<PlotPoint>, gapThresholdMs: Long): List<MoodSegment> {
    if (points.size < 2) return emptyList()
    val raw = mutableListOf<MoodSegment>()
    for (i in 0 until points.lastIndex) {
        val start = points[i].instant.toEpochMilli()
        val end = points[i + 1].instant.toEpochMilli()
        if (end <= start) continue
        val isGap = (end - start) > gapThresholdMs
        val state = if (isGap) null else normalizedMoodLabel(points[i].state)
        val last = raw.lastOrNull()
        if (last != null && last.isGap == isGap && last.state == state && last.endMs == start) {
            raw[raw.lastIndex] = last.copy(endMs = end)
        } else {
            raw.add(MoodSegment(start, end, state, isGap))
        }
    }
    return raw
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MoodTimelineChart(title: String, history: List<HistoryPoint>) {
    val points = remember(history) {
        history.mapNotNull { point ->
            val time = parseReportInstant(point.date) ?: return@mapNotNull null
            moodLevel(point.state) ?: return@mapNotNull null
            PlotPoint(time, 0.0, normalizedMoodLabel(point.state))
        }.sortedBy { it.instant }
    }
    val gapThresholdMs = remember(points) { detectGapThresholdMs(points) }
    val segments = remember(points, gapThresholdMs) { buildMoodSegments(points, gapThresholdMs) }
    val entries = remember(points, segments) {
        buildList {
            points.forEach { p ->
                val ms = p.instant.toEpochMilli()
                add(
                    ChartInspectionEntry(
                        startMs = ms,
                        endMs = ms,
                        title = p.state ?: "Sin datos",
                        timeLabel = localReportTime(p.instant.toString()),
                        subtitle = "Observación puntual de la jaula",
                        isGap = false,
                    )
                )
            }
            segments.filter { it.isGap }.forEach { gap ->
                val startStr = Instant.ofEpochMilli(gap.startMs).toString()
                val endStr = Instant.ofEpochMilli(gap.endMs).toString()
                add(
                    ChartInspectionEntry(
                        startMs = gap.startMs,
                        endMs = gap.endMs,
                        title = "Período sin datos",
                        timeLabel = "${localHourOnly(startStr)} – ${localHourOnly(endStr)}",
                        subtitle = "La cámara o el monitor no registraron mediciones",
                        isGap = true,
                    )
                )
            }
        }.sortedWith(compareBy<ChartInspectionEntry> { it.startMs }.thenBy { it.isGap })
    }

    var selectedIndex by remember(entries) {
        val lastObsIndex = entries.indexOfLast { !it.isGap }.takeIf { it >= 0 } ?: 0
        mutableIntStateOf(lastObsIndex)
    }

    Surface(
        color = PureWhite,
        shape = MaterialTheme.shapes.large,
        border = BorderStroke(1.dp, WarmOutline),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = InkText)
            if (points.isEmpty()) {
                EmptyState("Sin observaciones en este rango", "Cambia el rango o espera nuevos reportes del monitor.")
                return@Surface
            }

            val latest = points.last()
            val (latestBg, latestFg) = moodColors(latest.state)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(NinfasSpacing.sm),
            ) {
                Surface(
                    color = latestBg,
                    shape = RoundedCornerShape(999.dp),
                    border = if (latestBg == SageFilter) BorderStroke(1.dp, ForestGreen.copy(alpha = 0.25f)) else null,
                ) {
                    Text(
                        text = "${latest.state} a las ${localHourOnly(latest.instant.toString())}",
                        style = tabularStyle(MaterialTheme.typography.labelLarge),
                        color = latestFg,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                    )
                }
            }
            Text(
                "Corresponde a la jaula completa",
                style = MaterialTheme.typography.bodySmall,
                color = SlateSecondary,
            )

            val firstTime = points.first().instant.toEpochMilli()
            val lastTime = points.last().instant.toEpochMilli()
            val totalSpan = (lastTime - firstTime).coerceAtLeast(1L)
            val hasGaps = segments.any { it.isGap }
            val onlyIsolatedPoints = points.size == 1 || (segments.isNotEmpty() && segments.all { it.isGap })
            val selectedEntry = entries[selectedIndex.coerceIn(entries.indices)]

            if (points.size == 1) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .background(GapSand)
                        .border(1.dp, WarmOutline, RoundedCornerShape(12.dp)),
                    contentAlignment = Alignment.Center,
                ) {
                    val (dotBg, dotFg) = moodColors(latest.state)
                    Surface(
                        color = dotBg,
                        shape = RoundedCornerShape(999.dp),
                    ) {
                        Text(
                            text = "${latest.state} · ${localHourOnly(latest.instant.toString())}",
                            style = tabularStyle(MaterialTheme.typography.labelMedium),
                            color = dotFg,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                        )
                    }
                }
            } else {
                BoxWithConstraints(Modifier.fillMaxWidth()) {
                    val totalWidthDp = maxWidth
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(48.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .border(1.dp, WarmOutline, RoundedCornerShape(12.dp))
                            .semantics {
                                contentDescription =
                                    "$title. ${points.size} observaciones. Toca un tramo o marca para ver la hora y el estado."
                            },
                    ) {
                        segments.forEach { segment ->
                            val fraction = ((segment.endMs - segment.startMs).toFloat() / totalSpan.toFloat())
                                .coerceAtLeast(0.02f)
                            val segmentWidthDp = totalWidthDp * fraction
                            val (bg, fg) = if (segment.isGap) GapSand to SlateSecondary else moodColors(segment.state)
                            val isSelected = selectedEntry.isGap == segment.isGap &&
                                selectedEntry.startMs >= segment.startMs &&
                                selectedEntry.endMs <= segment.endMs
                            Box(
                                modifier = Modifier
                                    .weight(fraction)
                                    .fillMaxHeight()
                                    .background(bg)
                                    .then(
                                        if (isSelected) Modifier.border(2.dp, InkText)
                                        else Modifier
                                    )
                                    .clickable {
                                        val matchIdx = if (segment.isGap) {
                                            entries.indexOfFirst { it.isGap && it.startMs == segment.startMs }
                                        } else {
                                            val mid = (segment.startMs + segment.endMs) / 2L
                                            entries.indices
                                                .filter { !entries[it].isGap }
                                                .minByOrNull { abs(entries[it].startMs - mid) }
                                        }
                                        if (matchIdx != null && matchIdx >= 0) selectedIndex = matchIdx
                                    },
                                contentAlignment = Alignment.Center,
                            ) {
                                if (segmentWidthDp >= 56.dp) {
                                    Text(
                                        text = if (segment.isGap) "Sin datos" else segment.state.orEmpty(),
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.Medium,
                                        color = fg,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        modifier = Modifier.padding(horizontal = 4.dp),
                                    )
                                }
                            }
                        }
                    }
                }

                // Real-time point markers track beneath the strip
                Canvas(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(20.dp)
                        .pointerInput(points, entries) {
                            detectTapGestures { pos ->
                                val target = firstTime + ((pos.x / size.width).coerceIn(0f, 1f) * totalSpan).toLong()
                                val nearestObs = points.indices.minByOrNull {
                                    abs(points[it].instant.toEpochMilli() - target)
                                } ?: 0
                                val targetMs = points[nearestObs].instant.toEpochMilli()
                                val entryIdx = entries.indexOfFirst { !it.isGap && it.startMs == targetMs }
                                if (entryIdx >= 0) selectedIndex = entryIdx
                            }
                        },
                ) {
                    val inset = 6.dp.toPx()
                    val width = (size.width - inset * 2).coerceAtLeast(1f)
                    val cy = size.height / 2f
                    drawLine(WarmOutline, Offset(inset, cy), Offset(size.width - inset, cy), strokeWidth = 1.5.dp.toPx())
                    points.forEach { point ->
                        val px = inset + ((point.instant.toEpochMilli() - firstTime).toFloat() / totalSpan.toFloat() * width)
                        val (dotColor, _) = moodColors(point.state)
                        val active = !selectedEntry.isGap && selectedEntry.startMs == point.instant.toEpochMilli()
                        if (active) {
                            drawCircle(InkText, 6.5.dp.toPx(), Offset(px, cy))
                        }
                        drawCircle(dotColor, if (active) 4.5.dp.toPx() else 3.5.dp.toPx(), Offset(px, cy))
                    }
                }
            }

            if (onlyIsolatedPoints && points.size > 1) {
                Text(
                    "Observaciones puntuales: las marcas indican las horas reales registradas.",
                    style = MaterialTheme.typography.labelSmall,
                    color = SlateSecondary,
                )
            }

            TimeAxisRow(firstTime = firstTime, lastTime = lastTime, showMid = points.size > 2)

            // Color + text legend so every state is always clear regardless of segment width
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                val presentStates = points.mapNotNull { it.state }.distinct()
                presentStates.forEach { stateName ->
                    val (dotColor, _) = moodColors(stateName)
                    LegendChip(label = stateName, color = dotColor)
                }
                if (hasGaps) {
                    LegendChip(label = "Sin datos", color = GapSand, bordered = true)
                }
            }

            InspectionPanel(
                title = selectedEntry.title,
                timeText = selectedEntry.timeLabel,
                extra = selectedEntry.subtitle,
                canPrevious = selectedIndex > 0,
                canNext = selectedIndex < entries.lastIndex,
                onPrevious = { selectedIndex = (selectedIndex - 1).coerceAtLeast(0) },
                onNext = { selectedIndex = (selectedIndex + 1).coerceAtMost(entries.lastIndex) },
            )
        }
    }
}

@Composable
private fun ActivityLineChart(title: String, history: List<HistoryPoint>) {
    val points = remember(history) {
        history.mapNotNull { point ->
            val time = parseReportInstant(point.date) ?: return@mapNotNull null
            if (!point.value.isFinite()) return@mapNotNull null
            PlotPoint(time, point.value, point.state)
        }.sortedBy { it.instant }
    }
    val gapThresholdMs = remember(points) { detectGapThresholdMs(points) }
    var selected by remember(points) { mutableIntStateOf((points.size - 1).coerceAtLeast(0)) }

    Surface(
        color = PureWhite,
        shape = MaterialTheme.shapes.large,
        border = BorderStroke(1.dp, WarmOutline),
    ) {
        Column(
            Modifier.fillMaxWidth().padding(NinfasSpacing.lg),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = InkText)
            if (points.isEmpty()) {
                EmptyState("Sin observaciones en este rango", "Cambia el rango o espera nuevos reportes del monitor.")
                return@Surface
            }

            Text(
                "Desplazamiento en la jaula (% de la diagonal de cámara por minuto)",
                style = MaterialTheme.typography.labelMedium,
                color = InkText,
            )
            Text(
                "100 % equivale a cruzar toda la imagen en un minuto; hasta 5 % indica aves tranquilas.",
                style = MaterialTheme.typography.labelSmall,
                color = SlateSecondary,
            )

            val firstTime = points.first().instant.toEpochMilli()
            val lastTime = points.last().instant.toEpochMilli()
            val span = (lastTime - firstTime).coerceAtLeast(1).toDouble()
            val top = max(5.0, points.maxOf { it.value } * 1.1)
            val bottom = minOf(0.0, points.minOf { it.value })
            val selectedPoint = points[selected.coerceIn(points.indices)]
            val hasGaps = (1 until points.size).any {
                (points[it].instant.toEpochMilli() - points[it - 1].instant.toEpochMilli()) > gapThresholdMs
            }

            Row(Modifier.fillMaxWidth().height(168.dp)) {
                Column(
                    Modifier.width(46.dp).fillMaxHeight(),
                    verticalArrangement = Arrangement.SpaceBetween,
                ) {
                    listOf(number(top), number((top + bottom) / 2), number(bottom)).forEach {
                        Text(
                            it,
                            style = tabularStyle(MaterialTheme.typography.labelSmall),
                            color = SlateSecondary,
                            maxLines = 1,
                        )
                    }
                }
                Canvas(
                    Modifier
                        .weight(1f)
                        .fillMaxHeight()
                        .semantics {
                            contentDescription =
                                "$title. ${points.size} observaciones. Toca para seleccionar una; también puedes usar los botones Anterior y Siguiente."
                        }
                        .pointerInput(points) {
                            detectTapGestures { position ->
                                val target = firstTime + ((position.x / size.width).coerceIn(0f, 1f) * span).toLong()
                                selected = points.indices.minByOrNull { abs(points[it].instant.toEpochMilli() - target) } ?: 0
                            }
                        },
                ) {
                    val inset = 6.dp.toPx()
                    val width = (size.width - inset * 2).coerceAtLeast(1f)
                    val height = (size.height - inset * 2).coerceAtLeast(1f)
                    fun x(point: PlotPoint) = if (points.size == 1) inset + width / 2 else
                        inset + ((point.instant.toEpochMilli() - firstTime) / span * width).toFloat()
                    fun y(point: PlotPoint) = inset + ((top - point.value) / (top - bottom) * height).toFloat()

                    // Shaded vertical bands for intervals without measurements
                    for (index in 1 until points.size) {
                        val prev = points[index - 1]
                        val curr = points[index]
                        if (curr.instant.toEpochMilli() - prev.instant.toEpochMilli() > gapThresholdMs) {
                            val gx0 = x(prev)
                            val gx1 = x(curr)
                            drawRect(
                                color = GapSand.copy(alpha = 0.65f),
                                topLeft = Offset(gx0, inset),
                                size = Size((gx1 - gx0).coerceAtLeast(2f), height),
                            )
                        }
                    }

                    // Horizontal reference lines
                    for (index in 0..2) {
                        val gridY = inset + index * height / 2
                        drawLine(WarmOutline, Offset(inset, gridY), Offset(size.width - inset, gridY), strokeWidth = 1.dp.toPx())
                    }

                    // Line path broken across gaps so stopped camera != low activity
                    val path = Path()
                    points.forEachIndexed { index, point ->
                        val px = x(point)
                        val py = y(point)
                        if (index == 0) {
                            path.moveTo(px, py)
                        } else {
                            val dt = point.instant.toEpochMilli() - points[index - 1].instant.toEpochMilli()
                            if (dt > gapThresholdMs) {
                                path.moveTo(px, py)
                            } else {
                                path.lineTo(px, py)
                            }
                        }
                    }
                    drawPath(path, ForestGreen, style = Stroke(width = 2.dp.toPx()))

                    // Point dots so peaks and isolated observations after gaps stay clearly visible
                    points.forEach { point ->
                        drawCircle(ForestGreen, 3.dp.toPx(), Offset(x(point), y(point)))
                    }

                    val selectedX = x(selectedPoint)
                    drawLine(
                        color = InkText.copy(alpha = .4f),
                        start = Offset(selectedX, inset),
                        end = Offset(selectedX, size.height - inset),
                        strokeWidth = 1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)),
                    )
                    drawCircle(PureWhite, 7.dp.toPx(), Offset(selectedX, y(selectedPoint)))
                    drawCircle(ForestGreen, 5.dp.toPx(), Offset(selectedX, y(selectedPoint)))
                }
            }

            TimeAxisRow(
                firstTime = firstTime,
                lastTime = lastTime,
                showMid = points.size > 2,
                startPadding = 46.dp,
            )

            if (hasGaps) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Box(
                        Modifier
                            .size(12.dp)
                            .background(GapSand, RoundedCornerShape(3.dp))
                            .border(1.dp, WarmOutline, RoundedCornerShape(3.dp)),
                    )
                    Text(
                        "La línea se corta en períodos sin mediciones para distinguirlos de baja actividad.",
                        style = MaterialTheme.typography.labelSmall,
                        color = SlateSecondary,
                    )
                }
            }

            InspectionPanel(
                title = "${number(selectedPoint.value)} % diagonal/min",
                timeText = localReportTime(selectedPoint.instant.toString()),
                extra = selectedPoint.state?.takeIf { it.isNotBlank() },
                canPrevious = selected > 0,
                canNext = selected < points.lastIndex,
                onPrevious = { selected = (selected - 1).coerceAtLeast(0) },
                onNext = { selected = (selected + 1).coerceAtMost(points.lastIndex) },
            )
        }
    }
}

@Composable
private fun TimeAxisRow(
    firstTime: Long,
    lastTime: Long,
    showMid: Boolean,
    startPadding: androidx.compose.ui.unit.Dp = 0.dp,
) {
    val firstStr = localHourOnly(Instant.ofEpochMilli(firstTime).toString())
    val midStr = localHourOnly(Instant.ofEpochMilli((firstTime + lastTime) / 2L).toString())
    val lastStr = localHourOnly(Instant.ofEpochMilli(lastTime).toString())
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = startPadding),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(firstStr, style = tabularStyle(MaterialTheme.typography.labelSmall), color = SlateSecondary)
        if (showMid && lastTime > firstTime && midStr != firstStr && midStr != lastStr) {
            Text(midStr, style = tabularStyle(MaterialTheme.typography.labelSmall), color = SlateSecondary)
        }
        if (lastTime > firstTime) {
            Text(lastStr, style = tabularStyle(MaterialTheme.typography.labelSmall), color = SlateSecondary)
        }
    }
}

@Composable
private fun LegendChip(label: String, color: Color, bordered: Boolean = false) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Box(
            Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(color)
                .then(if (bordered) Modifier.border(1.dp, WarmOutline, CircleShape) else Modifier),
        )
        Text(label, style = MaterialTheme.typography.labelSmall, color = SlateSecondary)
    }
}

@Composable
private fun InspectionPanel(
    title: String,
    timeText: String,
    extra: String?,
    canPrevious: Boolean,
    canNext: Boolean,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
) {
    Surface(color = IvoryBackground, shape = MaterialTheme.shapes.medium) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onPrevious, enabled = canPrevious) {
                Icon(
                    Icons.Outlined.ChevronLeft,
                    "Observación anterior",
                    tint = if (canPrevious) ForestGreen else SlateSecondary.copy(alpha = 0.4f),
                )
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(title, style = tabularStyle(MaterialTheme.typography.titleSmall), color = InkText)
                Text(timeText, style = tabularStyle(MaterialTheme.typography.bodySmall), color = SlateSecondary)
                if (!extra.isNullOrBlank()) {
                    Text(extra, style = MaterialTheme.typography.labelSmall, color = SlateSecondary)
                }
            }
            IconButton(onClick = onNext, enabled = canNext) {
                Icon(
                    Icons.Outlined.ChevronRight,
                    "Observación siguiente",
                    tint = if (canNext) ForestGreen else SlateSecondary.copy(alpha = 0.4f),
                )
            }
        }
    }
}
