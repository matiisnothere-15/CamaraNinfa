package cl.ninfas.monitor.data

import java.util.concurrent.TimeUnit
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class NinfasApiTest {
    private lateinit var server: MockWebServer
    private lateinit var client: OkHttpClient
    private lateinit var api: NinfasApi

    @Before fun startHttpsServer() {
        val certificate = HeldCertificate.Builder().addSubjectAlternativeName("localhost")
            .addSubjectAlternativeName("127.0.0.1").addSubjectAlternativeName("::1").build()
        val serverTls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
        val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
        server = MockWebServer()
        server.useHttps(serverTls.sslSocketFactory(), false)
        server.start()
        client = OkHttpClient.Builder().sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager)
            .readTimeout(2, TimeUnit.SECONDS).build()
        api = NinfasApi(server.url("/ninfas/").toString(), "private-test-key", client)
    }

    @After fun stopServer() {
        server.shutdown()
        client.connectionPool.evictAll()
        client.dispatcher.executorService.shutdown()
    }

    @Test fun normalizeRejectsUnsafeOrAmbiguousUrls() {
        listOf("http://example.test", "https://user:secret@example.test", "https://@example.test", "https://example.test?", "https://example.test#", "https://example.test?key=secret", "https://example.test/#x", "example.test", "").forEach {
            assertThrows(ApiException::class.java) { NinfasApi.normalizeUrl(it) }
        }
        assertEquals("https://example.test/ninfas", NinfasApi.normalizeUrl(" https://EXAMPLE.test/ninfas/ "))
    }

    @Test fun snapshotUsesAllSevenRoutesAndSelectedHoursWithoutSendingKeyToReads() = runBlocking {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when (request.requestUrl!!.encodedPath) {
                "/ninfas/api/health" -> MockResponse().setBody(HEALTH)
                "/ninfas/api/estado" -> MockResponse().setBody("{}")
                "/ninfas/api/aves_stats" -> MockResponse().setBody("""{"aves":[],"sin_identificar":2}""")
                else -> MockResponse().setBody("[]")
            }
        }
        val snapshot = api.snapshot(168)
        assertTrue(snapshot.metrics.isEmpty())
        assertEquals(2, snapshot.stats.unidentified)
        assertEquals("ok", snapshot.health.status)
        val requests = (1..7).map { server.takeRequest(2, TimeUnit.SECONDS)!! }
        assertEquals(setOf("/ninfas/api/health", "/ninfas/api/estado", "/ninfas/api/historial?horas=168", "/ninfas/api/acciones?horas=168", "/ninfas/api/recomendaciones", "/ninfas/api/aves", "/ninfas/api/aves_stats?horas=168"), requests.map { it.path }.toSet())
        assertTrue(requests.all { it.getHeader("X-Ninfas-Admin-Key") == null })
    }

    @Test fun aFailedSnapshotResourceThrowsInsteadOfCreatingEmptyData() = runBlocking {
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse = when (request.requestUrl!!.encodedPath) {
                "/ninfas/api/health" -> MockResponse().setBody(HEALTH)
                "/ninfas/api/estado" -> MockResponse().setResponseCode(503).setBody("""{"detail":"Base no disponible"}""")
                "/ninfas/api/aves_stats" -> MockResponse().setBody("""{"aves":[],"sin_identificar":0}""")
                else -> MockResponse().setBody("[]")
            }
        }
        val error = captureApiError { api.snapshot(24) }
        assertEquals(503, error.statusCode)
        assertTrue(error.message!!.contains("Base no disponible"))
    }

    @Test fun writesAndAssistantUseAdminHeaderAndSpanishPayloads() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        server.enqueue(MockResponse().setBody("""{"respuesta":"Bien","fuente":"Microsoft Foundry"}"""))
        api.createBird("Mushu", "Gris", "Observación")
        api.deleteBird(9)
        assertEquals("Bien", api.ask("¿Cómo está?").answer)
        val create = server.takeRequest()
        val delete = server.takeRequest()
        val ask = server.takeRequest()
        assertEquals("POST", create.method)
        assertEquals("Mushu", JSONObject(create.body.readUtf8()).getString("nombre"))
        assertEquals("DELETE", delete.method)
        assertEquals("/ninfas/api/aves/9", delete.path)
        assertEquals("¿Cómo está?", JSONObject(ask.body.readUtf8()).getString("pregunta"))
        listOf(create, delete, ask).forEach {
            assertEquals("private-test-key", it.getHeader("X-Ninfas-Admin-Key"))
            assertNull(it.getHeader("Origin"))
            assertNull(it.getHeader("Sec-Fetch-Site"))
        }
    }

    @Test fun redirectsNeverForwardAdminCredentials() = runBlocking {
        val other = MockWebServer()
        other.start()
        try {
            server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", other.url("/stolen")))
            val error = captureApiError { api.createBird("Mushu", "", "") }
            assertEquals(307, error.statusCode)
            assertNull(other.takeRequest(300, TimeUnit.MILLISECONDS))
        } finally { other.shutdown() }
    }

    @Test fun httpsRedirectsAreRejectedEvenWithinTheSameServer() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(307).setHeader("Location", server.url("/stolen")))
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        assertEquals(307, captureApiError { api.deleteBird(4) }.statusCode)
        server.takeRequest()
        assertNull(server.takeRequest(300, TimeUnit.MILLISECONDS))
    }

    @Test fun publicClientRejectsUntrustedTlsCertificates() = runBlocking {
        val productionClient = NinfasApi(server.url("/").toString())
        captureApiError { productionClient.health() }
        assertEquals(0, server.requestCount)
    }

    @Test fun plainTextHostErrorAndStructuredValidationErrorsStayReadable() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(400).setBody("Invalid host header"))
        assertTrue(captureApiError { api.health() }.message!!.contains("Invalid host header"))
        server.enqueue(MockResponse().setResponseCode(422).setBody("""{"detail":[{"loc":["body","nombre"],"msg":"String should have at most 50 characters","type":"string_too_long"}]}"""))
        val validation = captureApiError { api.createBird("Mushu", "", "") }
        assertEquals(422, validation.statusCode)
        assertTrue(validation.message!!.contains("nombre"))
        assertTrue(validation.message!!.contains("50"))
    }

    @Test fun rateLimitReportsRetryAfterWithoutRetrying() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(429).setHeader("Retry-After", "120").setBody("""{"detail":"Demasiadas consultas"}"""))
        val error = captureApiError { api.ask("Estado") }
        assertEquals(120L, error.retryAfterSeconds)
        assertEquals(429, error.statusCode)
        assertEquals(1, server.requestCount)
    }

    @Test fun writesAreNotRetriedAfterServerConsumesRequestAndDisconnects() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        val error = captureApiError { api.deleteBird(4) }
        assertNull(error.statusCode)
        assertTrue(error.message!!.contains("confirmar"))
        assertEquals(1, server.requestCount)
    }

    @Test fun a503WithImmediateRetryAfterDoesNotReplaySensitiveOperations() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "0").setBody("""{"detail":"Servicio ocupado"}"""))
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        val error = captureApiError { api.deleteBird(4) }
        assertEquals(503, error.statusCode)
        assertEquals(1, server.requestCount)
    }

    @Test fun immediateRetryAfterDoesNotReplayBirdCreation() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "0"))
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        assertEquals(503, captureApiError { api.createBird("Mushu", "", "") }.statusCode)
        assertEquals(1, server.requestCount)
    }

    @Test fun immediateRetryAfterDoesNotReplayAssistantQueries() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "0"))
        server.enqueue(MockResponse().setBody("""{"respuesta":"Bien","fuente":"Microsoft Foundry"}"""))
        assertEquals(503, captureApiError { api.ask("Estado") }.statusCode)
        assertEquals(1, server.requestCount)
    }

    @Test fun invalidResponseAndUnconfirmedMutationAreRejected() = runBlocking<Unit> {
        server.enqueue(MockResponse().setBody("<html>Unavailable</html>"))
        assertNull(captureApiError { api.health() }.statusCode)
        server.enqueue(MockResponse().setBody("""{"ok":false}"""))
        captureApiError { api.createBird("Mushu", "", "") }
    }

    @Test fun localValidationRejectsOutOfBoundsInputsBeforeNetwork() = runBlocking {
        listOf<suspend () -> Unit>({ api.createBird(" ", "", "") }, { api.createBird("x".repeat(51), "", "") }, { api.createBird("Mushu", "x".repeat(101), "") }, { api.createBird("Mushu", "", "x".repeat(501)) }, { api.deleteBird(0) }, { api.ask(" ") }, { api.ask("x".repeat(601)) }, { api.snapshot(0) }, { api.snapshot(169) }).forEach { captureApiError(it) }
        assertEquals(0, server.requestCount)
    }

    @Test fun validationCountsUnicodeCodepointsLikeTheServer() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        server.enqueue(MockResponse().setBody("""{"respuesta":"Bien","fuente":"Microsoft Foundry"}"""))
        api.createBird("🐦".repeat(50), "🟡".repeat(100), "🐦".repeat(500))
        api.ask("🐦".repeat(600))
        assertEquals(2, server.requestCount)
        assertEquals("🐦".repeat(50), JSONObject(server.takeRequest().body.readUtf8()).getString("nombre"))
    }

    private suspend fun captureApiError(block: suspend () -> Unit): ApiException {
        try { block() } catch (error: ApiException) { return error }
        throw AssertionError("Se esperaba ApiException")
    }

    companion object {
        const val HEALTH = """{"status":"ok","base_datos_disponible":true,"monitor_activo":true,"ultimo_snapshot_utc":"2026-11-18T05:00:00.123456+00:00","minutos_sin_reporte":0.5,"lotes_pendientes_respaldo":0}"""
    }
}
