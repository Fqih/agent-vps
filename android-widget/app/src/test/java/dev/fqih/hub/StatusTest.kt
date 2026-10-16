package dev.fqih.hub

import org.json.JSONException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StatusTest {
    private val live = """
        {"updated":"2026-10-16T11:18:12+07:00",
         "jobs":{"new_matches":4,"drafts":0,"active":1,"interview":0,"followup_due":0},
         "today":{"items":[{"time":"10:00","title":"Interview PT X","kind":"event"},
                           {"time":null,"title":"Follow-up Y","kind":"followup"}],"calendar":"ok"},
         "queue":{"running":0,"queued":2,"failed":1},
         "vps":{"cpu":13,"ram":49,"disk":23,"down":["site:demo"],"backup_ok":true},
         "router":{"ag":"10/11","cx":"1/1","gh":"1/1"},
         "level":"warn"}
    """.trimIndent()

    @Test
    fun parsesLiveShape() {
        val s = Status.parse(live)
        assertEquals("warn", s.level)
        assertEquals("2026-10-16T11:18:12+07:00", s.updated)
        assertEquals(Jobs(4, 1, 0, 0), s.jobs)
        assertEquals(listOf(Agenda("10:00", "Interview PT X"), Agenda(null, "Follow-up Y")), s.today!!.items)
        assertEquals("ok", s.today!!.calendar)
        assertEquals(Queue(0, 2, 1), s.queue)
        assertEquals(Vps(13, 49, 23, listOf("site:demo"), true), s.vps)
        assertEquals(mapOf("ag" to "10/11", "cx" to "1/1", "gh" to "1/1"), s.router)
    }

    @Test
    fun errorOrMissingSectionIsNull() {
        val s = Status.parse("""{"level":"crit","jobs":{"error":"database is locked"},"router":{"error":"x"}}""")
        assertNull(s.jobs)
        assertNull(s.today)
        assertNull(s.vps)
        assertEquals(emptyMap<String, String>(), s.router)
        assertEquals("crit", s.level)
    }

    @Test(expected = JSONException::class)
    fun rejectsNonJson() {
        Status.parse("<html>login</html>")
    }
}
