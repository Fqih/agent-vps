package dev.fqih.hub

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId
import java.time.ZonedDateTime

class PhoneAgendaTest {
    private val wib = ZoneId.of("Asia/Jakarta")

    @Test
    fun timedEventCarriesOffsetAndLocalDate() {
        val begin = ZonedDateTime.of(2026, 10, 17, 0, 30, 0, 0, wib).toInstant().toEpochMilli()
        val e = JSONObject(PhoneAgenda.toJson(listOf(PhoneEvent(7, "Subuh", begin, false)), wib))
            .getJSONArray("events").getJSONObject(0)
        assertEquals("7:$begin", e.getString("id"))
        assertEquals("2026-10-17T00:30+07:00", e.getString("start"))
        assertEquals("2026-10-17", e.getString("date"))
        assertEquals(false, e.getBoolean("all_day"))
    }

    @Test
    fun allDayDateComesFromUtcMidnight() {
        // Android stores all-day instances at UTC midnight; in WIB that is 07:00 the same day.
        val begin = ZonedDateTime.of(2026, 10, 18, 0, 0, 0, 0, ZoneId.of("UTC")).toInstant().toEpochMilli()
        val e = JSONObject(PhoneAgenda.toJson(listOf(PhoneEvent(8, "Libur", begin, true)), ZoneId.of("America/Los_Angeles")))
            .getJSONArray("events").getJSONObject(0)
        assertEquals("2026-10-18", e.getString("date"))
        assertTrue(e.isNull("start"))
        assertEquals(true, e.getBoolean("all_day"))
    }

    @Test
    fun blankTitleIsKeptForServerDefault() {
        val json = PhoneAgenda.toJson(listOf(PhoneEvent(1, "", 0, false)), wib)
        assertEquals("", JSONObject(json).getJSONArray("events").getJSONObject(0).getString("title"))
    }
}
