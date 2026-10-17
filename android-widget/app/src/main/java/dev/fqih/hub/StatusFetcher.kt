package dev.fqih.hub

import org.json.JSONException
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Short, fixed messages: they go straight into the widget header and must never contain the URL. */
class FetchError(message: String) : Exception(message)

object StatusFetcher {
    /** One blocking GET; call it off the main thread. Success carries JSON that Status.parse accepts. */
    fun fetch(url: String, timeoutMs: Int = 10_000): Result<String> = request(url, timeoutMs, null) { conn ->
        val body = conn.inputStream.bufferedReader().use { it.readText() }
        Status.parse(body)
        body
    }

    /** One blocking JSON POST (the phone agenda); success means the Hub stored it. */
    fun post(url: String, json: String, timeoutMs: Int = 10_000): Result<Unit> = request(url, timeoutMs, json) { }

    private fun <T> request(url: String, timeoutMs: Int, json: String?, read: (HttpURLConnection) -> T): Result<T> = try {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        conn.instanceFollowRedirects = false // a redirect could carry the token out of the tailnet
        try {
            if (json != null) {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(json.toByteArray()) }
            }
            when (val code = conn.responseCode) {
                200, 204 -> Result.success(read(conn))
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
