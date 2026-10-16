package dev.fqih.hub

import java.time.LocalDate
import java.time.ZoneOffset

object Format {
    private val WIB = ZoneOffset.ofHours(7)

    /** Server time, prefixed with the day ("16/10 11:18") when it is not from [today]. */
    fun stamp(iso: String?, today: LocalDate): String {
        val time = clock(iso)
        val date = iso?.takeIf { it.length >= 10 }?.let { runCatching { LocalDate.parse(it.substring(0, 10)) }.getOrNull() }
        return if (date == null || date == today) time else "%02d/%02d %s".format(date.dayOfMonth, date.monthValue, time)
    }

    /** "2026-10-16T11:18:12+07:00" -> "11:18"; the server already sends WIB. */
    fun clock(iso: String?): String =
        iso?.takeIf { it.length >= 16 && it[13] == ':' }?.substring(11, 16) ?: "--:--"

    /** Header right side: setup hint, loading, error, or the server time with the error in front. */
    fun header(status: Status?, error: String?, configured: Boolean, today: LocalDate = LocalDate.now(WIB)): String =
        when {
            !configured -> "Buka app untuk setup"
            status == null -> error ?: "Memuat…"
            error != null -> "$error · ${stamp(status.updated, today)}"
            else -> stamp(status.updated, today)
        }

    fun router(map: Map<String, String>): String =
        if (map.isEmpty()) "–" else map.toSortedMap().entries.joinToString(" · ") { "${it.key} ${it.value}" }
}
