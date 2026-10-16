package dev.fqih.hub

object Format {
    /** "2026-10-16T11:18:12+07:00" -> "11:18"; the server already sends WIB. */
    fun clock(iso: String?): String =
        iso?.takeIf { it.length >= 16 && it[13] == ':' }?.substring(11, 16) ?: "--:--"

    /** Header right side: setup hint, loading, error, or the server time with the error in front. */
    fun header(status: Status?, error: String?, configured: Boolean): String = when {
        !configured -> "Buka app untuk setup"
        status == null -> error ?: "Memuat…"
        error != null -> "$error · ${clock(status.updated)}"
        else -> clock(status.updated)
    }

    fun router(map: Map<String, String>): String =
        if (map.isEmpty()) "–" else map.toSortedMap().entries.joinToString(" · ") { "${it.key} ${it.value}" }
}
