package cl.ninfas.monitor.ui

import cl.ninfas.monitor.data.ActionEvent
import java.time.Instant
import java.time.ZoneId
import org.junit.Assert.*
import org.junit.Test

class UiHelpersTest {
    @Test fun `missing or malformed timestamps never become current time`() {
        assertNull(parseReportInstant(null))
        assertNull(parseReportInstant(""))
        assertNull(parseReportInstant("not a date"))
        assertEquals("Sin fecha", localReportTime(null, ZoneId.of("UTC")))
        assertEquals("--:--", localHourOnly(null, ZoneId.of("UTC")))
        assertEquals("Sin fecha", localDayHeader(null, null, ZoneId.of("UTC")))
    }

    @Test fun `offsets microseconds and legacy naive UTC timestamps keep their instant`() {
        val expected = Instant.parse("2026-11-18T12:34:56.123456Z")
        val santiago = ZoneId.of("America/Santiago")
        assertEquals(expected, parseReportInstant("2026-11-18T12:34:56.123456"))
        assertEquals(expected, parseReportInstant("2026-11-18T09:34:56.123456-03:00"))
        assertEquals("18 nov, 09:34", localReportTime(expected.toString(), santiago))
        assertEquals("09:34", localHourOnly(expected.toString(), santiago))
    }

    @Test fun `caregiver titles describe visits naturally and distinguish confirmed ingestion`() {
        val mushuWater = ActionEvent("2026-11-18T22:10:00Z", "Hidratacion", 5.4, "Fin", null, null, "Mushu")
        assertEquals("Mushu visitó el bebedero", formatCaregiverEventTitle(mushuWater))
        assertEquals("Estuvo allí 5,4 segundos", formatCaregiverDuration(mushuWater))

        val unknownFood = ActionEvent("2026-11-18T14:00:00Z", "Alimentacion", 0.0, "Fin", null, 409, null)
        assertEquals("Un ave visitó el comedero", formatCaregiverEventTitle(unknownFood))
        assertNull(formatCaregiverDuration(unknownFood))

        val confirmedDrink = mushuWater.copy(state = "Ingesta confirmada")
        assertEquals("Mushu bebió agua", formatCaregiverEventTitle(confirmedDrink))

        val confirmedEat = unknownFood.copy(bird = "Yukki", state = "Confirmado")
        assertEquals("Yukki comió", formatCaregiverEventTitle(confirmedEat))
    }

    @Test fun `legacy notes strip technical tokens pipes and jpg filenames`() {
        val legacy = ActionEvent(
            date = "2026-11-18T22:10:00Z",
            action = "Hidratacion",
            duration = 0.0,
            state = "Fin",
            notes = "Estado=BEBIENDO | Duracion=5.4s | Ave=track #409 | Motivo=track_perdido | Evidencia=evidencia_20261118_010756.jpg",
            track = 409,
            bird = null,
        )
        assertEquals("Un ave visitó el bebedero", formatCaregiverEventTitle(legacy))
        assertEquals("Estuvo allí 5,4 segundos", formatCaregiverDuration(legacy))
        assertNull(sanitizeLegacyNotes(legacy.notes))

        val legacyWithName = legacy.copy(
            action = "Alimentacion",
            notes = "Estado=COMIENDO | Duracion=12.0s | Ave=Mushu | Motivo=cambio_estado | Percha lateral"
        )
        assertEquals("Mushu visitó el comedero", formatCaregiverEventTitle(legacyWithName))
        assertEquals("Percha lateral", sanitizeLegacyNotes(legacyWithName.notes))
    }

    @Test fun `visit pluralization and initials handle singular zero and unicode`() {
        assertEquals("0 visitas", formatVisitCount(0))
        assertEquals("1 visita", formatVisitCount(1))
        assertEquals("2 visitas", formatVisitCount(2))
        assertEquals("M", birdInitial(" mushu "))
        assertEquals("?", birdInitial("  "))
    }

    @Test fun `actions group chronologically by day and deduplicate captures`() {
        val santiago = ZoneId.of("America/Santiago")
        val now = Instant.parse("2026-11-18T15:30:00Z")
        val todayWater = ActionEvent("2026-11-18T15:30:00Z", "Hidratacion", 8.0, "Fin", null, null, "Mushu")
        val todayFood = ActionEvent("2026-11-18T13:15:00Z", "Alimentacion", 12.0, "Fin", null, null, "Yukki")
        val yesterdayWater = ActionEvent("2026-11-17T18:00:00Z", "Hidratacion", 6.0, "Fin", null, null, "Mushu")

        val merged = combineActions(listOf(todayWater), listOf(todayFood, todayWater, yesterdayWater))
        assertEquals(3, merged.size)

        val grouped = groupActionsByDay(merged, now, santiago)
        assertEquals(2, grouped.size)
        assertEquals("Hoy · 18 nov", grouped[0].first)
        assertEquals(listOf(todayWater, todayFood), grouped[0].second)
        assertEquals("Ayer · 17 nov", grouped[1].first)
        assertEquals(listOf(yesterdayWater), grouped[1].second)
    }

    @Test fun `degraded or inactive monitor cannot be shown as live`() {
        val now = Instant.parse("2026-11-18T12:00:00Z")
        assertFalse(monitorIsCurrent("degraded", true, true, now.toString(), now))
        assertFalse(monitorIsCurrent("ok", true, false, now.toString(), now))
        assertFalse(monitorIsCurrent("ok", false, true, now.toString(), now))
        assertFalse(monitorIsCurrent("ok", true, true, null, now))
        assertTrue(monitorIsCurrent("ok", true, true, now.toString(), now))
    }

    @Test fun `stale and future reports cannot be shown as live`() {
        val now = Instant.parse("2026-11-18T12:00:00Z")
        assertFalse(monitorIsCurrent("ok", true, true, now.minusSeconds(301).toString(), now))
        assertFalse(monitorIsCurrent("ok", true, true, now.plusSeconds(61).toString(), now))
        assertTrue(monitorIsCurrent("ok", true, true, now.minusSeconds(300).toString(), now))
    }

    @Test fun `unknown moods are absent rather than normal in the chart`() {
        assertNull(moodLevel(null))
        assertNull(moodLevel("Unknown"))
        assertEquals(0.0, moodLevel("Desesperado")!!, 0.0)
        assertEquals(3.0, moodLevel("Comodo")!!, 0.0)
        assertEquals(3.0, moodLevel("Cómodo")!!, 0.0)
    }

    @Test fun `bird form bounds match the server and trim the name`() {
        assertNotNull(birdInputError("   ", "", ""))
        assertNull(birdInputError(" Mushu ", "a".repeat(100), "n".repeat(500)))
        assertNotNull(birdInputError("a".repeat(51), "", ""))
        assertNotNull(birdInputError("Mushu", "a".repeat(101), ""))
        assertNotNull(birdInputError("Mushu", "", "n".repeat(501)))
    }

    @Test fun `unicode bird names count the same characters as the server`() {
        assertNull(birdInputError("🐦".repeat(50), "🟡".repeat(100), "🪶".repeat(500)))
        assertNotNull(birdInputError("🐦".repeat(51), "", ""))
    }
}
