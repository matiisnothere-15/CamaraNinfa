package cl.ninfas.monitor.alerts

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import cl.ninfas.monitor.MainActivity
import cl.ninfas.monitor.R
import cl.ninfas.monitor.data.NinfasApi
import cl.ninfas.monitor.data.Recommendation
import cl.ninfas.monitor.settings.ConnectionGuard
import cl.ninfas.monitor.settings.ConnectionSnapshot
import cl.ninfas.monitor.settings.ConnectionStore
import java.time.Instant
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

class AlertWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val store = ConnectionStore(applicationContext)
        val connection = synchronized(ConnectionGuard.lock) {
            store.snapshot().takeIf { isCurrent(it) }
        } ?: return Result.success()
        return try {
            // Care polling is read-only and never needs the administrative credential.
            val api = NinfasApi(connection.settings.baseUrl)
            val health = api.health()
            val recommendations = api.recommendations()
            synchronized(ConnectionGuard.lock) {
                val current = store.snapshot()
                if (!isStopped && isCurrent(current) && current.generation == connection.generation) {
                    val decision = AlertPolicy.evaluate(readState(connection.generation), health, recommendations, Instant.now())
                    if (decision.usable) {
                        // Persist first: a process death after notify must not repeat the same alert.
                        saveState(connection.generation, decision.state)
                        decision.notifications.forEach(::notify)
                    }
                }
            }
            Result.success()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // Network/health failures are shown in the UI. Wait for the next periodic run.
            Result.success()
        }
    }

    private fun isCurrent(snapshot: ConnectionSnapshot): Boolean =
        snapshot.settings.baseUrl.isNotBlank() && snapshot.settings.backgroundAlerts &&
            snapshot.generation.isNotEmpty() &&
            snapshot.generation == inputData.getString(AlertScheduler.GENERATION_KEY)

    private fun readState(generation: String): AlertState {
        val preferences = applicationContext.getSharedPreferences(AlertScheduler.STATE_PREFERENCES, Context.MODE_PRIVATE)
        if (preferences.getString("generation", "") != generation) return AlertState()
        return try {
            val json = JSONObject(preferences.getString("active", "{}") ?: "{}")
            val active = buildMap {
                val keys = json.keys()
                while (keys.hasNext()) {
                    val title = keys.next()
                    put(title, json.getString(title))
                }
            }
            AlertState(preferences.getBoolean("initialized", false), active)
        } catch (_: Exception) {
            AlertState()
        }
    }

    private fun saveState(generation: String, state: AlertState) {
        check(applicationContext.getSharedPreferences(AlertScheduler.STATE_PREFERENCES, Context.MODE_PRIVATE).edit()
            .putString("generation", generation)
            .putBoolean("initialized", state.initialized)
            .putString("active", JSONObject(state.active).toString())
            .commit()) { "No se pudo guardar el estado de los avisos." }
    }

    private fun notify(recommendation: Recommendation) {
        if (Build.VERSION.SDK_INT >= 33 &&
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val manager = applicationContext.getSystemService(NotificationManager::class.java)
        if (!manager.areNotificationsEnabled()) return
        AlertScheduler.createChannel(applicationContext)
        val openApp = PendingIntent.getActivity(applicationContext, 0,
            Intent(applicationContext, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val priority = if (recommendation.level == "urgente") "Urgente" else "Atención"
        val notification = Notification.Builder(applicationContext, AlertScheduler.CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_ninfa)
            .setContentTitle("$priority: ${recommendation.title}")
            .setContentText(recommendation.detail)
            .setStyle(Notification.BigTextStyle().bigText(recommendation.detail))
            .setCategory(Notification.CATEGORY_STATUS)
            .setContentIntent(openApp)
            .setAutoCancel(true)
            .build()
        val id = AlertPolicy.identity(recommendation.title).hashCode() and Int.MAX_VALUE
        manager.notify(id, notification)
    }
}
