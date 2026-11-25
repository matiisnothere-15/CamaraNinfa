package cl.ninfas.monitor.ui

import android.app.Application
import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import cl.ninfas.monitor.data.ActionEvent
import cl.ninfas.monitor.data.ApiException
import cl.ninfas.monitor.data.AssistantReply
import cl.ninfas.monitor.data.Health
import cl.ninfas.monitor.data.NinfasApi
import cl.ninfas.monitor.data.Snapshot
import cl.ninfas.monitor.settings.BirdPhotoStore
import cl.ninfas.monitor.settings.ConnectionSettings
import cl.ninfas.monitor.settings.ConnectionStore
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class NinfasUiState(
    val connection: ConnectionSettings = ConnectionSettings(),
    val snapshot: Snapshot? = null,
    val hours: Int = 24,
    val loading: Boolean = false,
    val error: String? = null,
    val now: Instant = Instant.now(),
    val checking: Boolean = false,
    val checkedHealth: Health? = null,
    val checkMessage: String? = null,
    val checkError: Boolean = false,
    val writing: Boolean = false,
    val mutationMessage: String? = null,
    val mutationError: Boolean = false,
    val assistantBusy: Boolean = false,
    val assistantReply: AssistantReply? = null,
    val assistantError: String? = null,
    val birdPhotos: Map<Int, String> = emptyMap(),
    val capturedActions: List<ActionEvent> = emptyList(),
)

class NinfasViewModel(application: Application) : AndroidViewModel(application) {
    private val store = ConnectionStore(application)
    private val photoStore = BirdPhotoStore(application)
    private val initial = runCatching { store.read() }
    private val initialPhotos = runCatching { photoStore.readAll() }.getOrDefault(emptyMap())
    private val mutable = MutableStateFlow(
        NinfasUiState(
            connection = initial.getOrDefault(ConnectionSettings()),
            error = initial.exceptionOrNull()?.let { "No se pudo leer la conexión guardada. Configúrala de nuevo." },
            birdPhotos = initialPhotos,
        )
    )
    val state = mutable.asStateFlow()
    internal var clock: () -> Instant = { Instant.now() }
    internal var autoRefreshEnabled: Boolean = true
    private var generation = 0L
    private var readGeneration = 0L
    private var checkGeneration = 0L
    private var active = false
    private var poll: Job? = null
    private var readJob: Job? = null
    private var checkJob: Job? = null
    private var writeJob: Job? = null
    private var assistantJob: Job? = null

    fun setForeground(foreground: Boolean) {
        if (active == foreground) return
        active = foreground
        poll?.cancel()
        if (foreground) {
            if (autoRefreshEnabled) {
                refresh()
                poll = viewModelScope.launch {
                    while (isActive) {
                        delay(60_000)
                        refresh()
                    }
                }
            }
        } else {
            readGeneration++
            checkGeneration++
            readJob?.cancel()
            checkJob?.cancel()
            if (mutable.value.assistantBusy) {
                assistantJob?.cancel()
                mutable.update {
                    it.copy(
                        assistantBusy = false,
                        assistantError = "Consulta interrumpida. Puede haberse procesado; no se volverá a enviar automáticamente.",
                    )
                }
            }
            if (mutable.value.writing) {
                writeJob?.cancel()
                mutable.update {
                    it.copy(
                        writing = false,
                        mutationError = true,
                        mutationMessage = "Operación interrumpida. Puede haberse aplicado; actualiza el catálogo antes de intentarlo otra vez.",
                    )
                }
            }
            mutable.update { it.copy(loading = false, checking = false) }
        }
    }

    fun refresh() {
        val settings = mutable.value.connection
        if (settings.baseUrl.isBlank() || readJob?.isActive == true) return
        val version = generation
        val request = ++readGeneration
        val hours = mutable.value.hours
        readJob = viewModelScope.launch {
            mutable.update { it.copy(loading = true, now = clock()) }
            try {
                val result = NinfasApi(settings.baseUrl, settings.adminKey).snapshot(hours)
                if (version == generation && request == readGeneration) {
                    mutable.update {
                        it.copy(snapshot = result, loading = false, error = null, now = clock())
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == generation && request == readGeneration) {
                    mutable.update {
                        it.copy(loading = false, error = readableError(error), now = clock())
                    }
                }
            }
        }
    }

    fun selectHours(hours: Int) {
        if (hours !in listOf(6, 24, 168) || hours == mutable.value.hours) return
        readJob?.cancel()
        readJob = null
        mutable.update { it.copy(hours = hours, snapshot = null, error = null, loading = false) }
        refresh()
    }

    fun assignBirdPhoto(birdId: Int, uri: Uri?) {
        if (uri == null || birdId <= 0) return
        val saved = photoStore.saveFromUri(birdId, uri) ?: return
        if (saved.isNotBlank()) {
            mutable.update { it.copy(birdPhotos = photoStore.readAll()) }
        }
    }

    fun rotateBirdPhoto(birdId: Int) {
        if (birdId <= 0) return
        val saved = photoStore.rotatePhoto(birdId) ?: return
        if (saved.isNotBlank()) {
            mutable.update { it.copy(birdPhotos = photoStore.readAll()) }
        }
    }

    internal fun assignBirdBitmap(birdId: Int, bitmap: Bitmap) {
        if (birdId <= 0) return
        photoStore.saveBitmap(birdId, bitmap)
        mutable.update { it.copy(birdPhotos = photoStore.readAll()) }
    }

    fun recordVisit(
        action: String,
        birdName: String?,
        durationSeconds: Double?,
        dateIso: String = clock().toString(),
    ) {
        val normalizedAction = when (action) {
            "Alimentacion", "Hidratacion" -> action
            else -> "Alimentacion"
        }
        val cleanBird = birdName?.trim()?.takeIf { it.isNotEmpty() }
        val durationValue = durationSeconds?.takeIf { it.isFinite() && it > 0.0 } ?: 0.0
        val event = ActionEvent(
            date = dateIso,
            action = normalizedAction,
            duration = durationValue,
            state = "Fin",
            notes = null,
            track = null,
            bird = cleanBird,
        )
        mutable.update {
            it.copy(
                capturedActions = listOf(event) + it.capturedActions,
                now = clock(),
            )
        }
    }

    fun checkConnection(url: String) {
        checkJob?.cancel()
        val request = ++checkGeneration
        val normalized = try {
            NinfasApi.normalizeUrl(url)
        } catch (error: Exception) {
            mutable.update {
                it.copy(checking = false, checkedHealth = null, checkError = true, checkMessage = readableError(error))
            }
            return
        }
        val version = generation
        checkJob = viewModelScope.launch {
            mutable.update { it.copy(checking = true, checkedHealth = null, checkMessage = null) }
            try {
                // Health never sends a saved key to a URL being edited.
                val health = NinfasApi(normalized).health()
                if (version == generation && request == checkGeneration) {
                    val live = monitorIsCurrent(
                        health.status,
                        health.databaseAvailable,
                        health.monitorActive,
                        health.lastSnapshot,
                        clock(),
                    )
                    mutable.update {
                        it.copy(
                            checking = false,
                            checkedHealth = health,
                            checkError = !live,
                            checkMessage = if (live) "Servidor y monitor disponibles."
                            else "Servidor accesible; monitor degradado o sin un reporte reciente.",
                        )
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == generation && request == checkGeneration) {
                    mutable.update {
                        it.copy(checking = false, checkError = true, checkMessage = readableError(error))
                    }
                }
            }
        }
    }

    fun clearConnectionCheck() {
        checkGeneration++
        checkJob?.cancel()
        mutable.update { it.copy(checking = false, checkedHealth = null, checkMessage = null) }
    }

    fun saveConnection(url: String, key: String, alerts: Boolean): Boolean {
        val normalized = try {
            NinfasApi.normalizeUrl(url)
        } catch (error: Exception) {
            mutable.update { it.copy(checkError = true, checkMessage = readableError(error)) }
            return false
        }
        val previous = mutable.value.connection
        val changedServer = normalized != previous.baseUrl
        invalidateRequests()
        try {
            if (changedServer) {
                mutable.value = NinfasUiState(
                    hours = mutable.value.hours,
                    birdPhotos = photoStore.readAll(),
                )
                store.save(ConnectionSettings(baseUrl = normalized, backgroundAlerts = false))
            }
            store.save(ConnectionSettings(normalized, key.trim(), alerts))
            mutable.value = NinfasUiState(
                connection = store.read(),
                hours = mutable.value.hours,
                birdPhotos = photoStore.readAll(),
                capturedActions = if (changedServer) emptyList() else mutable.value.capturedActions,
            )
            if (active && autoRefreshEnabled) refresh()
            return true
        } catch (error: Exception) {
            val saved = runCatching { store.read() }.getOrDefault(ConnectionSettings())
            mutable.value = NinfasUiState(
                connection = saved,
                birdPhotos = photoStore.readAll(),
                error = "No se pudo guardar la conexión. Revisa la configuración y vuelve a intentarlo.",
                checkError = true,
                checkMessage = "No se pudo guardar la conexión de forma segura.",
            )
            return false
        }
    }

    fun disconnect(): Boolean {
        invalidateRequests()
        return try {
            store.clear()
            mutable.value = NinfasUiState(birdPhotos = photoStore.readAll())
            true
        } catch (error: Exception) {
            mutable.update {
                it.copy(
                    checkError = true,
                    checkMessage = "No se pudo borrar la conexión guardada. Vuelve a intentarlo.",
                )
            }
            false
        }
    }

    fun createBird(name: String, color: String, notes: String) {
        val validation = birdInputError(name, color, notes)
        if (validation != null) {
            mutable.update { it.copy(mutationMessage = validation, mutationError = true) }
            return
        }
        mutate("Ninfa registrada.") { it.createBird(name.trim(), color.trim(), notes.trim()) }
    }

    fun deleteBird(id: Int) = mutate("Ninfa eliminada del catálogo.") { api ->
        api.deleteBird(id)
        photoStore.remove(id)
    }

    private fun mutate(success: String, operation: suspend (NinfasApi) -> Unit) {
        val settings = mutable.value.connection
        if (mutable.value.writing) return
        if (settings.adminKey.isBlank()) {
            mutable.update {
                it.copy(mutationMessage = "Añade la clave administrativa en Conexión.", mutationError = true)
            }
            return
        }
        val version = generation
        writeJob = viewModelScope.launch {
            mutable.update { it.copy(writing = true, mutationMessage = null) }
            try {
                operation(NinfasApi(settings.baseUrl, settings.adminKey))
                if (version == generation) {
                    mutable.update {
                        it.copy(
                            writing = false,
                            mutationMessage = success,
                            mutationError = false,
                            birdPhotos = photoStore.readAll(),
                        )
                    }
                    readJob?.cancel()
                    readJob = null
                    refresh()
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == generation) {
                    mutable.update {
                        it.copy(
                            writing = false,
                            mutationError = true,
                            mutationMessage = readableError(error) +
                                " Si se interrumpió la conexión, puede haberse aplicado. Actualiza antes de repetir.",
                        )
                    }
                }
            }
        }
    }

    fun dismissMutationMessage() = mutable.update { it.copy(mutationMessage = null) }

    fun ask(question: String) {
        val trimmed = question.trim()
        val settings = mutable.value.connection
        if (mutable.value.assistantBusy || trimmed.isEmpty() || characterCount(trimmed) > 600) return
        if (settings.adminKey.isBlank()) {
            mutable.update { it.copy(assistantError = "Añade la clave administrativa en Conexión para consultar.") }
            return
        }
        val version = generation
        assistantJob = viewModelScope.launch {
            mutable.update { it.copy(assistantBusy = true, assistantReply = null, assistantError = null) }
            try {
                val reply = NinfasApi(settings.baseUrl, settings.adminKey).ask(trimmed)
                if (version == generation) {
                    mutable.update { it.copy(assistantBusy = false, assistantReply = reply) }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == generation) {
                    mutable.update {
                        it.copy(
                            assistantBusy = false,
                            assistantError = readableError(error) +
                                " La pregunta puede haberse procesado. No se reenvió automáticamente.",
                        )
                    }
                }
            }
        }
    }

    internal fun seedForTest(
        baseUrl: String = "https://fixture.invalid",
        adminKey: String = "fixture-test-key",
        snapshot: Snapshot? = null,
        now: Instant = clock(),
    ) {
        mutable.update {
            it.copy(
                connection = ConnectionSettings(baseUrl = baseUrl, adminKey = adminKey),
                snapshot = snapshot,
                now = now,
                loading = false,
                error = null,
                birdPhotos = photoStore.readAll(),
            )
        }
    }

    private fun invalidateRequests() {
        generation++
        readGeneration++
        checkGeneration++
        readJob?.cancel(); readJob = null
        checkJob?.cancel(); checkJob = null
        writeJob?.cancel(); writeJob = null
        assistantJob?.cancel(); assistantJob = null
    }
}

internal fun readableError(error: Exception): String = when (error) {
    is ApiException -> when (error.statusCode) {
        401 -> "La clave administrativa no es válida. Revísala en Conexión."
        403 -> "El servidor rechazó el acceso. Revisa HTTPS y los permisos."
        429 -> error.retryAfterSeconds?.let { "Demasiadas solicitudes. Espera $it segundos antes de volver a intentarlo." }
            ?: "Demasiadas solicitudes. Espera antes de volver a intentarlo."
        502, 503 -> "El servicio no está disponible. Actualiza en unos momentos."
        else -> error.message?.take(240) ?: "No se pudo obtener una respuesta válida del servidor."
    }
    is IllegalArgumentException -> error.message?.take(240) ?: "Escribe una URL HTTPS válida."
    else -> "No se pudo conectar. Revisa la red, el acceso privado y la URL HTTPS."
}
