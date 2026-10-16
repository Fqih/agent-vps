package dev.fqih.hub

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.hubStore by preferencesDataStore("hub")

/** Everything the widget needs to draw without network. [url] is decrypted; null means not set up. */
data class Snapshot(val raw: String?, val error: String?, val url: String?, val bot: String?)

class Store(private val context: Context) {
    private object Keys {
        val url = stringPreferencesKey("url_enc")
        val bot = stringPreferencesKey("bot")
        val raw = stringPreferencesKey("raw")
        val error = stringPreferencesKey("error")
    }

    // A key lost on reinstall or a damaged blob reads as "not set up", never as a crash.
    private fun Preferences.decryptedUrl(): String? = this[Keys.url]?.let { runCatching { Vault.decrypt(it) }.getOrNull() }

    val snapshot: Flow<Snapshot> =
        context.hubStore.data.map { Snapshot(it[Keys.raw], it[Keys.error], it.decryptedUrl(), it[Keys.bot]) }

    suspend fun url(): String? = context.hubStore.data.first().decryptedUrl()

    suspend fun bot(): String? = context.hubStore.data.first()[Keys.bot]

    suspend fun saveSettings(url: String, bot: String) {
        context.hubStore.edit { p ->
            p[Keys.url] = Vault.encrypt(url.trim())
            if (bot.isBlank()) p.remove(Keys.bot) else p[Keys.bot] = bot.trim()
            p.remove(Keys.raw) // data from a previous URL must not show under the new one
            p.remove(Keys.error)
        }
    }

    suspend fun saveFetch(result: Result<String>) {
        context.hubStore.edit { p ->
            result.onSuccess { p[Keys.raw] = it; p.remove(Keys.error) }
                .onFailure { p[Keys.error] = it.message ?: "offline" }
        }
    }
}
