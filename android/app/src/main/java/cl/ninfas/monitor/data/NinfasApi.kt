package cl.ninfas.monitor.data

import java.io.IOException
import java.net.URI
import java.time.Duration
import java.time.Instant
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.suspendCancellableCoroutine
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import okio.BufferedSink
import org.json.JSONArray
import org.json.JSONObject

class ApiException(
    message: String,
    val statusCode: Int? = null,
    val retryAfterSeconds: Long? = null,
) : IOException(message)

class NinfasApi internal constructor(
    baseUrl: String,
    private val adminKey: String,
    httpClient: OkHttpClient,
) {
    constructor(baseUrl: String, adminKey: String = "") : this(baseUrl, adminKey, defaultClient)

    private val base = normalizeUrl(baseUrl).toHttpUrl()
    // Disable retries and both redirect policies even for an injected client.
    private val client = httpClient.newBuilder()
        .retryOnConnectionFailure(false).followRedirects(false).followSslRedirects(false).build()
    private val assistantClient = client.newBuilder()
        .readTimeout(90, TimeUnit.SECONDS).callTimeout(90, TimeUnit.SECONDS).build()

    suspend fun health(): Health = JsonParsers.health(get("health"))

    suspend fun recommendations(): List<Recommendation> = JsonParsers.recommendations(get("recomendaciones"))

    suspend fun snapshot(hours: Int): Snapshot {
        if (hours !in 1..168) throw ApiException("El período debe estar entre 1 y 168 horas.")
        return coroutineScope {
            val health = async { health() }
            val metrics = async { JsonParsers.metrics(get("estado")) }
            val history = async { JsonParsers.history(get("historial", hours)) }
            val actions = async { JsonParsers.actions(get("acciones", hours)) }
            val recommendations = async { recommendations() }
            val birds = async { JsonParsers.birds(get("aves")) }
            val stats = async { JsonParsers.stats(get("aves_stats", hours)) }
            Snapshot(health.await(), metrics.await(), history.await(), actions.await(),
                recommendations.await(), birds.await(), stats.await(), Instant.now())
        }
    }

    suspend fun createBird(name: String, color: String, notes: String) {
        if (name.isBlank() || name.codePointCount(0, name.length) !in 1..50) throw ApiException("El nombre debe tener entre 1 y 50 caracteres.")
        if (color.codePointCount(0, color.length) > 100) throw ApiException("El color admite hasta 100 caracteres.")
        if (notes.codePointCount(0, notes.length) > 500) throw ApiException("Las notas admiten hasta 500 caracteres.")
        val body = JSONObject().put("nombre", name).put("color", color).put("notas", notes)
        JsonParsers.confirmMutation(send(protectedRequest("aves").post(body.toString().oneShotBody()).build()))
    }

    suspend fun deleteBird(id: Int) {
        if (id <= 0) throw ApiException("Selecciona un ave válida.")
        JsonParsers.confirmMutation(send(protectedRequest("aves", id.toString()).delete("".oneShotBody()).build()))
    }

    suspend fun ask(question: String): AssistantReply {
        if (question.isBlank() || question.codePointCount(0, question.length) !in 1..600) throw ApiException("La pregunta debe tener entre 1 y 600 caracteres.")
        val body = JSONObject().put("pregunta", question).toString().oneShotBody()
        return JsonParsers.assistant(send(protectedRequest("asistente").post(body).build(), assistantClient))
    }

    private suspend fun get(resource: String, hours: Int? = null): String {
        val url = endpoint(resource).newBuilder().apply {
            if (hours != null) addQueryParameter("horas", hours.toString())
        }.build()
        return send(Request.Builder().url(url).header("Accept", "application/json").get().build())
    }

    private fun endpoint(vararg segments: String) = base.newBuilder().apply {
        // Add relative segments explicitly so a reverse proxy's path prefix is preserved.
        if (base.encodedPath.endsWith('/')) removePathSegment(base.pathSize - 1)
        addPathSegment("api")
        segments.forEach(::addPathSegment)
    }.build()

    private fun protectedRequest(vararg segments: String): Request.Builder {
        if (adminKey.isBlank()) throw ApiException("Configura la clave administrativa para esta operación.")
        if (adminKey.any { it.code !in 32..126 }) throw ApiException("La clave administrativa contiene caracteres no válidos.")
        return Request.Builder().url(endpoint(*segments)).header("Accept", "application/json")
            .header("X-Ninfas-Admin-Key", adminKey)
    }

    private fun String.oneShotBody(): RequestBody {
        val bytes = toByteArray(Charsets.UTF_8)
        return object : RequestBody() {
            override fun contentType() = jsonType
            override fun contentLength() = bytes.size.toLong()
            // OkHttp can otherwise replay HTTP 503/Retry-After: 0 independently of network retry policy.
            override fun isOneShot() = true
            override fun writeTo(sink: BufferedSink) { sink.write(bytes) }
        }
    }

    private suspend fun send(request: Request, transport: OkHttpClient = client): String =
        suspendCancellableCoroutine { continuation ->
            val call = transport.newCall(request)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, error: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(transportError(request).also { it.initCause(error) })
                }

                override fun onResponse(call: Call, response: Response) {
                    try {
                        val body = response.use {
                            val text = it.body?.string().orEmpty()
                            if (!it.isSuccessful) throw ApiException(httpMessage(it.code, text), it.code, retryAfter(it.header("Retry-After")))
                            text
                        }
                        if (continuation.isActive) continuation.resume(body)
                    } catch (error: IOException) {
                        if (continuation.isActive) continuation.resumeWithException(
                            if (error is ApiException) error else transportError(request).also { it.initCause(error) })
                    }
                }
            })
        }

    private fun transportError(request: Request): ApiException = if (request.method == "GET") {
        ApiException("No se pudo conectar con el servidor. Comprueba la conexión y vuelve a actualizar.")
    } else {
        ApiException("No se pudo confirmar si la operación se completó. Actualiza los datos antes de intentarlo otra vez.")
    }

    companion object {
        private val jsonType = "application/json; charset=utf-8".toMediaType()
        private val defaultClient by lazy {
            OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS)
                .callTimeout(15, TimeUnit.SECONDS).retryOnConnectionFailure(false)
                .followRedirects(false).followSslRedirects(false).build()
        }

        fun normalizeUrl(input: String): String {
            val value = input.trim()
            val uri = try { URI(value) } catch (_: Exception) { throw invalidUrl() }
            if (!uri.scheme.equals("https", ignoreCase = true) || uri.rawUserInfo != null || uri.rawQuery != null || uri.rawFragment != null) throw invalidUrl()
            val parsed = try { value.toHttpUrl() } catch (_: IllegalArgumentException) { throw invalidUrl() }
            if (parsed.scheme != "https" || parsed.username.isNotEmpty() || parsed.password.isNotEmpty()) throw invalidUrl()
            return parsed.toString().trimEnd('/')
        }

        private fun invalidUrl() = ApiException("Introduce una URL HTTPS válida, sin usuario, contraseña, consulta ni fragmento.")

        private fun retryAfter(value: String?): Long? {
            if (value == null) return null
            value.trim().toLongOrNull()?.let { return it.coerceAtLeast(0) }
            return try {
                val retryAt = ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant()
                Duration.between(Instant.now(), retryAt).seconds.coerceAtLeast(0)
            } catch (_: Exception) { null }
        }

        private fun httpMessage(code: Int, body: String): String {
            if (code in 300..399) return "El servidor respondió con una redirección. Comprueba la URL HTTPS configurada."
            val detail = try {
                when (val value = JSONObject(body).opt("detail")) {
                    is String -> value
                    is JSONArray -> (0 until value.length()).mapNotNull { index ->
                        val item = value.optJSONObject(index) ?: return@mapNotNull null
                        val field = item.optJSONArray("loc")?.let { loc ->
                            (0 until loc.length()).map { loc.optString(it) }.filter { it != "body" }.joinToString(".")
                        }.orEmpty()
                        val message = item.optString("msg", "Datos no válidos")
                        if (field.isBlank()) message else "$field: $message"
                    }.joinToString("; ")
                    else -> null
                }
            } catch (_: Exception) { null }
            return (detail?.takeIf { it.isNotBlank() } ?: body.takeIf { it.isNotBlank() }
                ?: when (code) {
                    401 -> "Clave administrativa no válida."
                    403 -> "Acceso rechazado. Comprueba HTTPS y la configuración del servidor."
                    429 -> "Demasiadas consultas. Espera antes de volver a intentarlo."
                    502, 503 -> "El servicio no está disponible temporalmente."
                    else -> "La solicitud fue rechazada por el servidor (HTTP $code)."
                }).take(500)
        }
    }
}
