package cl.ninfas.monitor.settings

import cl.ninfas.monitor.data.ApiException
import org.junit.Assert.assertEquals
import org.junit.Test

class ConnectionRulesTest {
    @Test fun `changing server removes the previous key even if caller copied it`() {
        val old = ConnectionSettings("https://old.example/", "private-key", true)
        val saved = ConnectionRules.prepare(old, old.copy(baseUrl = "https://new.example"))
        assertEquals("https://new.example", saved.baseUrl)
        assertEquals("", saved.adminKey)
    }

    @Test fun `same normalized server permits entering a new key`() {
        val old = ConnectionSettings("https://ninfas.example/", "", false)
        val saved = ConnectionRules.prepare(old, old.copy(baseUrl = "https://ninfas.example", adminKey = "new-key"))
        assertEquals("new-key", saved.adminKey)
    }

    @Test fun `empty server removes credentials and disables background work`() {
        val saved = ConnectionRules.prepare(ConnectionSettings(), ConnectionSettings("", "unused", true))
        assertEquals(ConnectionSettings(), saved)
    }

    @Test(expected = ApiException::class)
    fun `insecure server cannot be saved`() {
        ConnectionRules.prepare(ConnectionSettings(), ConnectionSettings("http://ninfas.example"))
    }
}
