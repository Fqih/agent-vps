package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Test

class FormatTest {
    private val status = Status("2026-10-16T11:18:12+07:00", "ok", null, null, null, null, emptyMap())

    @Test
    fun clockTakesHourMinute() {
        assertEquals("11:18", Format.clock("2026-10-16T11:18:12+07:00"))
        assertEquals("--:--", Format.clock(null))
        assertEquals("--:--", Format.clock("bad"))
    }

    @Test
    fun headerStates() {
        assertEquals("Buka app untuk setup", Format.header(null, null, configured = false))
        assertEquals("Memuat…", Format.header(null, null, configured = true))
        assertEquals("offline", Format.header(null, "offline", configured = true))
        assertEquals("11:18", Format.header(status, null, configured = true, today = java.time.LocalDate.of(2026, 10, 16)))
        assertEquals("offline · 11:18", Format.header(status, "offline", configured = true, today = java.time.LocalDate.of(2026, 10, 16)))
    }

    @Test
    fun olderDataShowsDate() {
        val today = java.time.LocalDate.of(2026, 10, 17)
        assertEquals("16/10 11:18", Format.header(status, null, configured = true, today = today))
        assertEquals("offline · 16/10 11:18", Format.header(status, "offline", configured = true, today = today))
    }

    @Test
    fun modelDropsProviderPrefix() {
        assertEquals("gemini-3.8-flash", Format.model("ag/gemini-3.8-flash"))
        assertEquals("", Format.model(null))
    }

    @Test
    fun taskIcons() {
        assertEquals(listOf("✓", "✗", "▶", "⏳", "•"), listOf("done", "failed", "running", "queued", "x").map(Format::taskIcon))
    }

    @Test
    fun vpsSummary() {
        assertEquals("up 7 hari · load 0.46", Format.vpsSummary(7, 0.46))
        assertEquals("load 0.46", Format.vpsSummary(null, 0.46))
        assertEquals("", Format.vpsSummary(null, null))
    }

    @Test
    fun routerSorted() {
        assertEquals("ag 10/11 · cx 1/1 · gh 1/1", Format.router(mapOf("gh" to "1/1", "ag" to "10/11", "cx" to "1/1")))
        assertEquals("–", Format.router(emptyMap()))
    }
}
