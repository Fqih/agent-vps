package dev.fqih.hub

import org.json.JSONException
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Short, fixed messages: they go straight into the widget header and must never contain the URL. */
class FetchError(message: String) : Exception(message)

object StatusFetcher {
    /** One blocking GET; call it off the main thread. Success carries JSON that Status.parse accepts. */
    fun fetch(url: String, timeoutMs: Int = 10_000): Result<String> = try {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        try {
            when (val code = conn.responseCode) {
                200 -> {
                    val body = conn.inputStream.bufferedReader().use { it.readText() }
                    Status.parse(body)
                    Result.success(body)
                }
                403 -> Result.failure(FetchError("token salah"))
                else -> Result.failure(FetchError("HTTP $code"))
            }
        } finally {
            conn.disconnect()
        }
    } catch (e: JSONException) {
        Result.failure(FetchError("data rusak"))
    } catch (e: IOException) {
        Result.failure(FetchError("offline"))
    }
}
