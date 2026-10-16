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
        assertEquals("11:18", Format.header(status, null, configured = true))
        assertEquals("offline · 11:18", Format.header(status, "offline", configured = true))
    }

    @Test
    fun routerSorted() {
        assertEquals("ag 10/11 · cx 1/1 · gh 1/1", Format.router(mapOf("gh" to "1/1", "ag" to "10/11", "cx" to "1/1")))
        assertEquals("–", Format.router(emptyMap()))
    }
}
