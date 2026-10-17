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

    /** "ag/gemini-3.8-flash" -> "gemini-3.8-flash"; the provider prefix only eats widget width. */
    fun model(name: String?): String = name?.substringAfter('/') ?: ""

    fun taskIcon(status: String): String = when (status) {
        "done" -> "✓"; "failed" -> "✗"; "running" -> "▶"; "queued" -> "⏳"; else -> "•"
    }

    fun vpsSummary(uptimeDays: Int?, load: Double?): String =
        listOfNotNull(uptimeDays?.let { "up $it hari" }, load?.let { "load %.2f".format(java.util.Locale.ROOT, it) })
            .joinToString(" · ")

    fun provider(q: Quota): String = q.name.replaceFirstChar { it.uppercase() }

    fun quotaName(q: Quota): String = provider(q) + when {
        q.missing > 0 -> " ${q.accounts - q.missing}/${q.accounts}"
        q.accounts > 1 -> " ×${q.accounts}"
        else -> ""
    }

    fun github(c: Contrib): String =
        "%,d setahun · streak %d · hari ini %d".format(java.util.Locale.forLanguageTag("id"), c.total, c.streak, c.today)
}
