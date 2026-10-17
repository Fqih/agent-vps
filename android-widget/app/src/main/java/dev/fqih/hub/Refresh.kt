package dev.fqih.hub

import android.content.Context
import androidx.glance.GlanceId
import androidx.glance.action.ActionParameters
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.updateAll
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

object Refresh {
    /** Fetch once, keep the old data on failure, redraw every widget. */
    suspend fun run(context: Context) {
        val store = Store(context)
        val url = store.url() ?: return
        // Agenda first, so the status fetched right after already shows it. A failed push only
        // means the Hub keeps the previous agenda; the status fetch reports any connection trouble.
        store.saveFetch(withContext(Dispatchers.IO) {
            PhoneAgenda.push(context, url)
            StatusFetcher.fetch(url)
        })
        HubWidget().updateAll(context)
    }

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<RefreshWorker>(30, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork("hub-refresh", ExistingPeriodicWorkPolicy.KEEP, request)
    }
}

class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Refresh.run(applicationContext)
        return Result.success()
    }
}

/** The ⟳ button: runs without a network constraint so "offline" shows at once when Tailscale is off. */
class RefreshAction : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        Refresh.run(context)
    }
}
