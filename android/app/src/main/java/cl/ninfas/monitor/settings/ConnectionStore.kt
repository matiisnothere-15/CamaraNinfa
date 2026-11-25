package cl.ninfas.monitor.settings

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import cl.ninfas.monitor.alerts.AlertScheduler
import cl.ninfas.monitor.data.NinfasApi
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class ConnectionSettings(
    val baseUrl: String = "",
    val adminKey: String = "",
    val backgroundAlerts: Boolean = false,
) {
    // Settings can reach diagnostic UI code; never expose the credential in toString().
    override fun toString(): String = "ConnectionSettings(baseUrl=$baseUrl, adminKey=[redacted], backgroundAlerts=$backgroundAlerts)"
}

internal object ConnectionRules {
    fun prepare(previous: ConnectionSettings, requested: ConnectionSettings): ConnectionSettings {
        if (requested.baseUrl.isBlank()) return ConnectionSettings()
        val normalized = NinfasApi.normalizeUrl(requested.baseUrl)
        val previousUrl = previous.baseUrl.takeIf { it.isNotBlank() }?.let { NinfasApi.normalizeUrl(it) }
        return requested.copy(
            baseUrl = normalized,
            adminKey = if (normalized != previousUrl) "" else requested.adminKey,
        )
    }
}

/** Serializes saves, resets, and the worker's final check + notification in this app process. */
internal object ConnectionGuard {
    val lock = Any()
}

internal data class ConnectionSnapshot(val settings: ConnectionSettings, val generation: String)

class ConnectionStore(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences("ninfas_connection", Context.MODE_PRIVATE)

    fun read(): ConnectionSettings = synchronized(ConnectionGuard.lock) { readLocked() }

    fun save(settings: ConnectionSettings) = synchronized(ConnectionGuard.lock) {
        val previous = readLocked()
        val next = ConnectionRules.prepare(previous, settings)
        if (previous == next) return@synchronized
        val encrypted = if (next.adminKey.isEmpty()) null else encrypt(next.adminKey, next.baseUrl)
        val editor = preferences.edit()
            .putString("base_url", next.baseUrl)
            .putBoolean("background_alerts", next.backgroundAlerts)
            .putString("generation", UUID.randomUUID().toString())
            .remove("key_ciphertext").remove("key_iv")
        if (encrypted != null) {
            editor.putString("key_ciphertext", encrypted.first).putString("key_iv", encrypted.second)
        }
        check(editor.commit()) { "No se pudo guardar la conexión en el dispositivo." }
        if (previous.baseUrl != next.baseUrl || next.adminKey.isEmpty()) deleteKey()
        AlertScheduler.reset(appContext)
        if (next.backgroundAlerts) AlertScheduler.configure(appContext, next)
    }

    fun clear() = synchronized(ConnectionGuard.lock) {
        // Removing the generation invalidates running workers, even if cancellation later fails.
        check(preferences.edit().clear().commit()) { "No se pudo eliminar la conexión del dispositivo." }
        deleteKey()
        AlertScheduler.reset(appContext)
    }

    internal fun snapshot(): ConnectionSnapshot = synchronized(ConnectionGuard.lock) {
        ConnectionSnapshot(readLocked(), preferences.getString("generation", "") ?: "")
    }

    internal fun invalidateAlerts() = synchronized(ConnectionGuard.lock) {
        check(preferences.edit().putString("generation", UUID.randomUUID().toString()).commit()) {
            "No se pudo actualizar la configuración de avisos."
        }
    }

    private fun readLocked(): ConnectionSettings {
        val baseUrl = preferences.getString("base_url", "") ?: ""
        if (baseUrl.isEmpty()) return ConnectionSettings()
        val ciphertext = preferences.getString("key_ciphertext", null)
        val iv = preferences.getString("key_iv", null)
        val key = if (ciphertext == null || iv == null) "" else {
            try {
                val cipher = Cipher.getInstance(TRANSFORMATION)
                cipher.init(Cipher.DECRYPT_MODE, secretKey(create = false), GCMParameterSpec(128, decode(iv)))
                cipher.updateAAD(baseUrl.toByteArray(Charsets.UTF_8))
                String(cipher.doFinal(decode(ciphertext)), Charsets.UTF_8)
            } catch (_: Exception) {
                // Keystore entries can disappear after device restore or a lock-screen change.
                preferences.edit().remove("key_ciphertext").remove("key_iv").commit()
                ""
            }
        }
        return ConnectionSettings(baseUrl, key, preferences.getBoolean("background_alerts", false))
    }

    private fun encrypt(value: String, baseUrl: String): Pair<String, String> {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey(create = true))
        cipher.updateAAD(baseUrl.toByteArray(Charsets.UTF_8))
        return encode(cipher.doFinal(value.toByteArray(Charsets.UTF_8))) to encode(cipher.iv)
    }

    private fun secretKey(create: Boolean): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val existing = store.getKey(KEY_ALIAS, null) as? SecretKey
        if (existing != null) return existing
        check(create) { "La clave guardada ya no está disponible." }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setKeySize(256)
                .build())
        }.generateKey()
    }

    private fun deleteKey() {
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(KEY_ALIAS)
    }

    private fun encode(bytes: ByteArray): String = Base64.encodeToString(bytes, Base64.NO_WRAP)
    private fun decode(value: String): ByteArray = Base64.decode(value, Base64.NO_WRAP)

    private companion object {
        const val KEY_ALIAS = "cl.ninfas.monitor.admin.v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
