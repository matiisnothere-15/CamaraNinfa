package cl.ninfas.monitor.alerts

import cl.ninfas.monitor.data.Health
import cl.ninfas.monitor.data.Recommendation
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AlertPolicyTest {
    private val now = Instant.parse("2026-11-18T12:00:00Z")
    private val health = Health("ok", true, true, "2026-11-18T11:59:00Z", 1.0, 0)
    private fun warning(detail: String = "Sin visitas observadas en 3 horas") =
        Recommendation("atencion", "Pocas visitas al bebedero", detail)

    @Test fun `first valid sample records baseline without notifying old alerts`() {
        val result = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now)
        assertTrue(result.state.initialized)
        assertTrue(result.notifications.isEmpty())
        assertEquals("atencion", result.state.active["pocas visitas al bebedero"])
    }

    @Test fun `new attention and urgent recommendations notify but info does not`() {
        val result = AlertPolicy.evaluate(
            AlertState(initialized = true), health,
            listOf(warning(), Recommendation("urgente", "Revisar jaula", "Observación reciente"),
                Recommendation("info", "Consejo", "Información")), now,
        )
        assertEquals(listOf("Pocas visitas al bebedero", "Revisar jaula"), result.notifications.map { it.title })
    }

    @Test fun `detail changes do not repeat an active alert`() {
        val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now).state
        val result = AlertPolicy.evaluate(baseline, health, listOf(warning("Ahora son 4 horas")), now)
        assertTrue(result.notifications.isEmpty())
    }

    @Test fun `escalation notifies once and a downgrade is silent`() {
        val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now).state
        val urgent = warning().copy(level = "urgente")
        val escalated = AlertPolicy.evaluate(baseline, health, listOf(urgent), now)
        assertEquals(listOf(urgent), escalated.notifications)
        assertTrue(AlertPolicy.evaluate(escalated.state, health, listOf(urgent), now).notifications.isEmpty())
        assertTrue(AlertPolicy.evaluate(escalated.state, health, listOf(warning()), now).notifications.isEmpty())
    }

    @Test fun `resolved recommendations rearm the next occurrence`() {
        val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now).state
        val resolved = AlertPolicy.evaluate(baseline, health, emptyList(), now).state
        assertTrue(resolved.active.isEmpty())
        assertEquals(listOf(warning()), AlertPolicy.evaluate(resolved, health, listOf(warning()), now).notifications)
    }

    @Test fun `healthy recommendation with same title resolves attention`() {
        val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now).state
        val resolved = AlertPolicy.evaluate(baseline, health, listOf(warning().copy(level = "bien")), now).state
        assertEquals(listOf(warning()), AlertPolicy.evaluate(resolved, health, listOf(warning()), now).notifications)
    }

    @Test fun `stale health never notifies or clears deduplication`() {
        val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(warning()), now).state
        val result = AlertPolicy.evaluate(baseline, health.copy(lastSnapshot = "2026-11-18T11:54:59Z"), emptyList(), now)
        assertFalse(result.usable)
        assertEquals(baseline, result.state)
    }

    @Test fun `invalid monitor health cannot establish a baseline`() {
        val invalid = listOf(
            health.copy(status = "degraded"), health.copy(databaseAvailable = false),
            health.copy(monitorActive = false), health.copy(pendingBatches = 1),
            health.copy(lastSnapshot = null), health.copy(lastSnapshot = "invalid"),
            health.copy(minutesWithoutReport = null), health.copy(minutesWithoutReport = 5.1),
            health.copy(minutesWithoutReport = Double.NaN),
        )
        invalid.forEach { sample ->
            val result = AlertPolicy.evaluate(AlertState(), sample, listOf(warning()), now)
            assertFalse(result.usable)
            assertFalse(result.state.initialized)
            assertTrue(result.notifications.isEmpty())
        }
    }

    @Test fun `freshness allows exactly five minutes and one future minute`() {
        assertTrue(AlertPolicy.evaluate(AlertState(), health.copy(lastSnapshot = "2026-11-18T11:55:00Z", minutesWithoutReport = 5.0), emptyList(), now).usable)
        assertTrue(AlertPolicy.evaluate(AlertState(), health.copy(lastSnapshot = "2026-11-18T12:01:00Z"), emptyList(), now).usable)
        assertFalse(AlertPolicy.evaluate(AlertState(), health.copy(lastSnapshot = "2026-11-18T12:01:00.001Z"), emptyList(), now).usable)
    }

    @Test fun `duplicate titles choose highest severity and ignore spelling case`() {
        val result = AlertPolicy.evaluate(
            AlertState(initialized = true), health,
            listOf(warning(), warning().copy(title = "  POCAS visitas al bebedero  ", level = "urgente")), now,
        )
        assertEquals(1, result.notifications.size)
        assertEquals("urgente", result.notifications.single().level)
    }

    @Test fun `changing hour counter in backend food and water titles does not repeat alerts`() {
        listOf("comer", "beber agua").forEach { action ->
            val first = Recommendation("atencion", "3.1 horas sin $action", "Sin visitas observadas")
            val baseline = AlertPolicy.evaluate(AlertState(), health, listOf(first), now).state
            val later = first.copy(title = "3.4 horas sin $action")
            val unchanged = AlertPolicy.evaluate(baseline, health, listOf(later), now)
            assertTrue(unchanged.notifications.isEmpty())
            val urgent = later.copy(level = "urgente", title = "6 horas sin $action")
            assertEquals(listOf(urgent), AlertPolicy.evaluate(unchanged.state, health, listOf(urgent), now).notifications)
        }
    }
}
