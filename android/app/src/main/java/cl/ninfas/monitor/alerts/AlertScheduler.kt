package cl.ninfas.monitor.alerts

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import cl.ninfas.monitor.settings.ConnectionGuard
import cl.ninfas.monitor.settings.ConnectionSettings
import cl.ninfas.monitor.settings.ConnectionStore
import java.util.concurrent.TimeUnit

object AlertScheduler {
    internal const val WORK_NAME = "ninfas_periodic_care"
    internal const val CHANNEL_ID = "ninfas_care"
    internal const val GENERATION_KEY = "connection_generation"
    internal const val STATE_PREFERENCES = "ninfas_alert_state"

    fun configure(context: Context, settings: ConnectionSettings) = synchronized(ConnectionGuard.lock) {
        val appContext = context.applicationContext
        val snapshot = ConnectionStore(appContext).snapshot()
        if (!settings.backgroundAlerts || settings.baseUrl.isBlank() ||
            !snapshot.settings.backgroundAlerts || snapshot.settings.baseUrl != settings.baseUrl) {
            reset(appContext)
            return@synchronized
        }
        createChannel(appContext)
        val request = PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInputData(workDataOf(GENERATION_KEY to snapshot.generation))
            .build()
        WorkManager.getInstance(appContext).enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
        Unit
    }

    fun reset(context: Context) = synchronized(ConnectionGuard.lock) {
        val appContext = context.applicationContext
        ConnectionStore(appContext).invalidateAlerts()
        check(appContext.getSharedPreferences(STATE_PREFERENCES, Context.MODE_PRIVATE).edit().clear().commit()) {
            "No se pudo restablecer el estado de los avisos."
        }
        appContext.getSystemService(NotificationManager::class.java).cancelAll()
        WorkManager.getInstance(appContext).cancelUniqueWork(WORK_NAME)
        Unit
    }

    internal fun createChannel(context: Context) {
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Cuidados de las ninfas", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Cambios recientes de atención o urgencia detectados por el monitor."
            },
        )
    }
}
