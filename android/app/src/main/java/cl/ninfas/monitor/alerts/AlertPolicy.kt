package cl.ninfas.monitor.alerts

import cl.ninfas.monitor.data.Health
import cl.ninfas.monitor.data.Recommendation
import java.text.Normalizer
import java.time.Instant
import java.time.format.DateTimeParseException
import java.util.Locale

data class AlertState(val initialized: Boolean = false, val active: Map<String, String> = emptyMap())
data class AlertDecision(val state: AlertState, val notifications: List<Recommendation>, val usable: Boolean)

object AlertPolicy {
    fun evaluate(state: AlertState, health: Health, recommendations: List<Recommendation>, now: Instant): AlertDecision {
        if (!isFresh(health, now)) return AlertDecision(state, emptyList(), false)
        val active = linkedMapOf<String, Recommendation>()
        recommendations.forEach { recommendation ->
            val title = identity(recommendation.title)
            val level = recommendation.level.trim().lowercase(Locale.ROOT)
            if (title.isNotEmpty() && rank(level) > rank(active[title]?.level)) {
                active[title] = recommendation.copy(level = level)
            }
        }
        val next = AlertState(initialized = true, active = active.mapValues { it.value.level })
        val notifications = if (!state.initialized) emptyList() else active.filter { (title, recommendation) ->
            rank(recommendation.level) > rank(state.active[title])
        }.values.toList()
        return AlertDecision(next, notifications, true)
    }

    private fun isFresh(health: Health, now: Instant): Boolean {
        if (health.status != "ok" || !health.databaseAvailable || !health.monitorActive || health.pendingBatches != 0) return false
        val minutes = health.minutesWithoutReport ?: return false
        if (!minutes.isFinite() || minutes !in -1.0..5.0) return false
        val snapshot = try {
            Instant.parse(health.lastSnapshot ?: return false)
        } catch (_: DateTimeParseException) {
            return false
        }
        return !snapshot.isBefore(now.minusSeconds(300)) && !snapshot.isAfter(now.plusSeconds(60))
    }

    private fun rank(level: String?): Int = when (level) {
        "atencion" -> 1
        "urgente" -> 2
        else -> 0
    }

    internal fun identity(title: String): String {
        val normalized = Normalizer.normalize(title, Normalizer.Form.NFC)
            .trim().replace(Regex("\\s+"), " ").lowercase(Locale.ROOT)
        // The existing API includes an elapsed-hours counter in these two titles.
        // Keep their condition stable while the counter changes, including across escalation.
        return normalized.replace(Regex("^\\d+(?:[.,]\\d+)? horas sin (comer|beber agua)$"), "horas sin $1")
    }
}
