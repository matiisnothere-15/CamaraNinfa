package cl.ninfas.monitor.settings

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.security.KeyStore
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ConnectionStoreDeviceTest {
    private lateinit var context: Context
    private lateinit var store: ConnectionStore

    @Before fun clearPreviousConnection() {
        context = InstrumentationRegistry.getInstrumentation().targetContext
        store = ConnectionStore(context)
        store.clear()
    }

    @After fun removeTestCredentials() {
        if (::store.isInitialized) store.clear()
    }

    @Test fun keySurvivesNewStoreInstanceWithoutPlaintextInPreferences() {
        // Enter the server first, then explicitly enter its credential on that same server.
        store.save(ConnectionSettings(baseUrl = SERVER_A))
        val settings = ConnectionSettings(SERVER_A, KEY_A, backgroundAlerts = false)
        store.save(settings)

        assertEquals(settings, ConnectionStore(context).read())
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        assertTrue(preferences.getString("key_ciphertext", null)?.isNotBlank() == true)
        assertTrue(preferences.getString("key_iv", null)?.isNotBlank() == true)
        assertFalse(preferences.all.values.any { it.toString().contains(KEY_A) })

        // Exercise the device's AndroidKeyStore, including its non-exportable key material.
        val key = androidKeyStore().getKey(KEY_ALIAS, null)
        assertNotNull(key)
        assertEquals("AES", key.algorithm)
        assertNull(key.encoded)
    }

    @Test fun changingServerDiscardsCopiedKeyAndClearDeletesTheNewCredential() {
        store.save(ConnectionSettings(baseUrl = SERVER_A))
        store.save(ConnectionSettings(SERVER_A, KEY_A, backgroundAlerts = false))
        val previous = store.read()
        assertEquals(KEY_A, previous.adminKey)

        store.save(previous.copy(baseUrl = SERVER_B))

        assertEquals(ConnectionSettings(baseUrl = SERVER_B), ConnectionStore(context).read())
        val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
        assertFalse(preferences.contains("key_ciphertext"))
        assertFalse(preferences.contains("key_iv"))
        assertFalse(androidKeyStore().containsAlias(KEY_ALIAS))

        store.save(ConnectionSettings(SERVER_B, KEY_B, backgroundAlerts = false))
        assertEquals(KEY_B, ConnectionStore(context).read().adminKey)
        store.clear()

        assertEquals(ConnectionSettings(), ConnectionStore(context).read())
        assertFalse(preferences.contains("base_url"))
        assertFalse(preferences.contains("key_ciphertext"))
        assertFalse(preferences.contains("key_iv"))
        assertFalse(preferences.all.values.any { it.toString().contains(KEY_A) || it.toString().contains(KEY_B) })
        assertFalse(androidKeyStore().containsAlias(KEY_ALIAS))
    }

    private fun androidKeyStore(): KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private companion object {
        const val SERVER_A = "https://example.com/ninfas"
        const val SERVER_B = "https://example.org/ninfas"
        const val KEY_A = "0123456789abcdef0123456789abcdef"
        const val KEY_B = "fedcba9876543210fedcba9876543210"
        const val PREFERENCES = "ninfas_connection"
        const val KEY_ALIAS = "cl.ninfas.monitor.admin.v1"
    }
}
