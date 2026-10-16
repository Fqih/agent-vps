package dev.fqih.hub

import java.net.URI

/** The app only ever talks to a Hub status URL inside the tailnet. */
object UrlRules {
    /** Null when [raw] is usable, otherwise the reason shown in settings. */
    fun problem(raw: String): String? {
        val uri = runCatching { URI(raw.trim()) }.getOrNull() ?: return "URL tidak valid"
        if (uri.scheme !in setOf("http", "https")) return "Harus diawali http:// atau https://"
        val host = uri.host ?: return "URL tidak valid"
        if (!isTailnet(host)) return "Host harus alamat Tailscale (100.x.x.x atau .ts.net)"
        if (uri.path != "/status") return "Path harus /status"
        val hasToken = uri.rawQuery?.split("&")?.any { it.startsWith("token=") && it.length > "token=".length } == true
        return if (hasToken) null else "Token belum ada di URL"
    }

    /** 100.64.0.0/10 (Tailscale CGNAT range) or a MagicDNS name. */
    fun isTailnet(host: String): Boolean {
        if (host.endsWith(".ts.net")) return true
        val parts = host.split(".").map { it.toIntOrNull() ?: return false }
        return parts.size == 4 && parts.all { it in 0..255 } && parts[0] == 100 && parts[1] in 64..127
    }

    /** hub-status serves the dashboard at / with the same token. Call only on a URL that passed [problem]. */
    fun dashboard(statusUrl: String): String = statusUrl.trim().replaceFirst("/status?", "/?")

    fun botProblem(raw: String): String? =
        if (raw.isBlank() || raw.trim().startsWith("https://")) null else "Link bot harus https://"
}
