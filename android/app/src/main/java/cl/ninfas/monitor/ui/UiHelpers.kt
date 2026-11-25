package cl.ninfas.monitor.ui

import cl.ninfas.monitor.data.ActionEvent
import cl.ninfas.monitor.data.Health
import java.time.Duration
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs

internal fun parseReportInstant(raw: String?): Instant? {
    val value = raw?.trim()?.takeIf { it.isNotEmpty() } ?: return null
    return runCatching { Instant.parse(value) }.getOrNull()
        ?: runCatching { OffsetDateTime.parse(value).toInstant() }.getOrNull()
        // Legacy SQL snapshots have no suffix but the API contract defines UTC.
        ?: runCatching { LocalDateTime.parse(value).toInstant(ZoneOffset.UTC) }.getOrNull()
}

private val ChileLocale = Locale.forLanguageTag("es-CL")
private val ReportFormat = DateTimeFormatter.ofPattern("dd MMM, HH:mm", ChileLocale)
private val HourFormat = DateTimeFormatter.ofPattern("HH:mm", ChileLocale)
private val DayShortFormat = DateTimeFormatter.ofPattern("d MMM", ChileLocale)
private val DayFullFormat = DateTimeFormatter.ofPattern("d 'de' MMMM", ChileLocale)

private val PlaceholderBirdRegex = Regex("""(?i)^(track\s*#?\d+|sin identificar|ave sin identificar|\?|none|null)$""")
private val LegacyAveRegex = Regex("""(?i)\bAve\s*=\s*([^|]+)""")
private val LegacyDurationRegex = Regex("""(?i)\bDuracion\s*=\s*([0-9]+(?:[.,][0-9]+)?)\s*s?""")
private val LegacyTechKeyRegex = Regex("""(?i)^(Estado|Duracion|Ave|Motivo|Evidencia)\s*=""")
private val LegacyTrackTokenRegex = Regex("""(?i)\btrack\s*#?\d+\b""")
private val LegacyImageFileRegex = Regex("""(?i)\S+\.(?:jpg|jpeg|png|webp)\b""")

internal fun localReportTime(raw: String?, zone: ZoneId = ZoneId.systemDefault()): String =
    parseReportInstant(raw)?.let { ReportFormat.withZone(zone).format(it) } ?: "Sin fecha"

internal fun localHourOnly(raw: String?, zone: ZoneId = ZoneId.systemDefault()): String =
    parseReportInstant(raw)?.let { HourFormat.withZone(zone).format(it) } ?: "--:--"

internal fun localDayHeader(raw: String?, now: Instant? = null, zone: ZoneId = ZoneId.systemDefault()): String {
    val instant = parseReportInstant(raw) ?: return "Sin fecha"
    val eventDate = instant.atZone(zone).toLocalDate()
    val today = now?.atZone(zone)?.toLocalDate()
    return when (eventDate) {
        today -> "Hoy · ${DayShortFormat.format(eventDate)}"
        today?.minusDays(1) -> "Ayer · ${DayShortFormat.format(eventDate)}"
        else -> DayFullFormat.format(eventDate)
    }
}

internal fun resolveEventBirdName(action: ActionEvent): String? {
    val direct = action.bird?.trim()?.takeIf { it.isNotEmpty() && !PlaceholderBirdRegex.matches(it) }
    if (direct != null) return direct
    val notes = action.notes ?: return null
    val match = LegacyAveRegex.find(notes)?.groupValues?.getOrNull(1)?.trim() ?: return null
    return match.takeIf { it.isNotEmpty() && !PlaceholderBirdRegex.matches(it) }
}

internal fun isConfirmedIngestion(action: ActionEvent): Boolean {
    val state = action.state?.trim().orEmpty()
    val kind = action.action.trim()
    return state.contains("Confirmad", ignoreCase = true) ||
        state.contains("Ingesta", ignoreCase = true) ||
        kind.contains("Confirmad", ignoreCase = true) ||
        kind.contains("Ingesta", ignoreCase = true)
}

internal fun formatCaregiverEventTitle(action: ActionEvent): String {
    val subject = resolveEventBirdName(action) ?: "Un ave"
    val confirmed = isConfirmedIngestion(action)
    return when (action.action) {
        "Hidratacion" -> if (confirmed) "$subject bebió agua" else "$subject visitó el bebedero"
        "Alimentacion" -> if (confirmed) "$subject comió" else "$subject visitó el comedero"
        "Observacion" -> "$subject en la jaula"
        else -> "$subject · ${action.action}"
    }
}

internal fun formatCaregiverDuration(action: ActionEvent): String? {
    val seconds = action.duration.takeIf { it.isFinite() && it > 0.0 }
        ?: action.notes?.let { notes ->
            LegacyDurationRegex.find(notes)?.groupValues?.getOrNull(1)
                ?.replace(',', '.')?.toDoubleOrNull()
                ?.takeIf { it.isFinite() && it > 0.0 }
        }
        ?: return null
    return if (abs(seconds - 1.0) < 0.05) "Estuvo allí 1 segundo"
    else "Estuvo allí ${number(seconds)} segundos"
}

internal fun sanitizeLegacyNotes(notes: String?): String? {
    val raw = notes?.trim()?.takeIf { it.isNotEmpty() } ?: return null
    val cleanSegments = raw.split('|').mapNotNull { segment ->
        val trimmed = segment.trim()
        when {
            trimmed.isEmpty() -> null
            LegacyTechKeyRegex.containsMatchIn(trimmed) -> null
            LegacyTrackTokenRegex.containsMatchIn(trimmed) -> null
            LegacyImageFileRegex.containsMatchIn(trimmed) -> null
            else -> trimmed
        }
    }
    return cleanSegments.takeIf { it.isNotEmpty() }?.joinToString(" · ")
}

internal fun formatVisitCount(visits: Int): String =
    if (visits == 1) "1 visita" else "$visits visitas"

internal fun birdInitial(name: String): String {
    val trimmed = name.trim()
    if (trimmed.isEmpty()) return "?"
    val firstCodePoint = trimmed.codePointAt(0)
    return String(Character.toChars(firstCodePoint)).uppercase(ChileLocale)
}

internal fun combineActions(captured: List<ActionEvent>, remote: List<ActionEvent>): List<ActionEvent> =
    (captured + remote)
        .distinctBy { Triple(it.date, it.action, resolveEventBirdName(it) ?: it.track?.toString().orEmpty()) }
        .sortedByDescending { parseReportInstant(it.date) ?: Instant.EPOCH }

internal fun groupActionsByDay(
    actions: List<ActionEvent>,
    now: Instant? = null,
    zone: ZoneId = ZoneId.systemDefault(),
): List<Pair<String, List<ActionEvent>>> {
    if (actions.isEmpty()) return emptyList()
    val ordered = actions.sortedByDescending { parseReportInstant(it.date) ?: Instant.EPOCH }
    val grouped = linkedMapOf<String, MutableList<ActionEvent>>()
    ordered.forEach { event ->
        val header = localDayHeader(event.date, now, zone)
        grouped.getOrPut(header) { mutableListOf() }.add(event)
    }
    return grouped.entries.map { it.key to it.value.toList() }
}

internal fun monitorIsCurrent(status: String, databaseAvailable: Boolean, monitorActive: Boolean,
                              lastSnapshot: String?, now: Instant): Boolean {
    if (status != "ok" || !databaseAvailable || !monitorActive) return false
    val report = parseReportInstant(lastSnapshot) ?: return false
    val age = Duration.between(report, now)
    return age >= Duration.ofSeconds(-60) && age <= Duration.ofMinutes(5)
}

internal fun currentHealth(health: Health, now: Instant): Boolean = monitorIsCurrent(
    health.status, health.databaseAvailable, health.monitorActive, health.lastSnapshot, now)

internal fun moodLevel(state: String?): Double? = when (state) {
    "Desesperado" -> 0.0
    "Estresado" -> 1.0
    "Normal" -> 2.0
    "Comodo", "Cómodo" -> 3.0
    else -> null
}

internal fun birdInputError(name: String, color: String, notes: String): String? = when {
    characterCount(name.trim()) !in 1..50 -> "El nombre debe tener entre 1 y 50 caracteres."
    characterCount(color) > 100 -> "El color admite hasta 100 caracteres."
    characterCount(notes) > 500 -> "Las notas admiten hasta 500 caracteres."
    else -> null
}

internal fun characterCount(value: String): Int = value.codePointCount(0, value.length)
