package cl.ninfas.monitor.data

import org.junit.Assert.*
import org.junit.Test

class JsonParsersTest {
    @Test fun healthPreservesDegradedStateAndNullableFreshness() {
        val health = JsonParsers.health("""{"status":"degraded","base_datos_disponible":false,"monitor_activo":false,"ultimo_snapshot_utc":null,"minutos_sin_reporte":null,"lotes_pendientes_respaldo":3}""")
        assertEquals("degraded", health.status)
        assertFalse(health.databaseAvailable)
        assertFalse(health.monitorActive)
        assertNull(health.lastSnapshot)
        assertNull(health.minutesWithoutReport)
        assertEquals(3, health.pendingBatches)
    }

    @Test fun metricsKeepUnknownNamesMicrosecondsAndNullState() {
        val metrics = JsonParsers.metrics("""{"NuevaMetrica":{"valor":2.75,"estado":null,"fecha":"2026-11-18T05:21:12.123456+00:00"}}""")
        assertEquals(1, metrics.size)
        assertEquals(2.75, metrics.getValue("NuevaMetrica").value, 0.0)
        assertNull(metrics.getValue("NuevaMetrica").state)
        assertEquals("2026-11-18T05:21:12.123456+00:00", metrics.getValue("NuevaMetrica").date)
    }

    @Test fun historyAndActionsPreserveUnassignedEvents() {
        val history = JsonParsers.history("""[{"fecha":"2026-11-18T05:00:00Z","metrica":"Animo","valor":4,"estado":null}]""")
        assertEquals(HistoryPoint("2026-11-18T05:00:00Z", "Animo", 4.0, null), history.single())
        val action = JsonParsers.actions("""[{"fecha":"2026-11-18T05:00:00Z","accion":"Alimentacion","duracion":7.5,"estado":"Fin","notas":null,"track":null,"ave":null}]""").single()
        assertEquals(7.5, action.duration, 0.0)
        assertEquals("Fin", action.state)
        assertNull(action.notes)
        assertNull(action.track)
        assertNull(action.bird)
    }

    @Test fun birdsAndStatsAcceptNullableMetadataWithoutInventingVisits() {
        val bird = JsonParsers.birds("""[{"id":4,"nombre":"Mushu","color":null,"notas":null,"registrada":null}]""").single()
        assertEquals(Bird(4, "Mushu", null, null, null), bird)
        val stats = JsonParsers.stats("""{"aves":[{"id":4,"nombre":"Mushu","color":null,"comidas":0,"seg_comiendo":0.0,"ultima_comida":null,"bebidas":2,"seg_bebiendo":4.5,"ultima_bebida":"2026-11-18T05:00:00.123456+00:00"}],"sin_identificar":7}""")
        assertEquals(7, stats.unidentified)
        assertEquals(0, stats.birds.single().foodVisits)
        assertNull(stats.birds.single().lastFood)
        assertEquals(2, stats.birds.single().waterVisits)
        assertEquals(4.5, stats.birds.single().waterSeconds, 0.0)
    }

    @Test fun recommendationsAndAssistantUseBackendFieldNames() {
        assertEquals(Recommendation("urgente", "Agua", "Sin visitas observadas"), JsonParsers.recommendations("""[{"nivel":"urgente","titulo":"Agua","detalle":"Sin visitas observadas"}]""").single())
        assertEquals(AssistantReply("Respuesta", "Microsoft Foundry"), JsonParsers.assistant("""{"respuesta":"Respuesta","fuente":"Microsoft Foundry"}"""))
    }

    @Test fun emptyCollectionsAreValidAbsenceOfRecords() {
        assertTrue(JsonParsers.metrics("{}").isEmpty())
        assertTrue(JsonParsers.history("[]").isEmpty())
        assertTrue(JsonParsers.actions("[]").isEmpty())
        assertTrue(JsonParsers.birds("[]").isEmpty())
        assertTrue(JsonParsers.recommendations("[]").isEmpty())
        assertEquals(Stats(emptyList(), 0), JsonParsers.stats("""{"aves":[],"sin_identificar":0}"""))
    }

    @Test fun invalidJsonOrMissingValuesFailInsteadOfBecomingZero() {
        listOf("not json", "[]", """{"x":{"estado":null,"fecha":"2026-11-18T05:00:00Z"}}""", """{"x":{"valor":null,"fecha":"2026-11-18T05:00:00Z"}}""", """{"x":{"valor":"bad","fecha":"2026-11-18T05:00:00Z"}}""").forEach { body ->
            assertThrows(ApiException::class.java) { JsonParsers.metrics(body) }
        }
        assertThrows(ApiException::class.java) { JsonParsers.stats("{}") }
        assertThrows(ApiException::class.java) { JsonParsers.health("{}") }
    }
}
