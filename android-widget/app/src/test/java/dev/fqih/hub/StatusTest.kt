package dev.fqih.hub

import org.json.JSONException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StatusTest {
    private val live = """
        {"updated":"2026-10-16T11:18:12+07:00",
         "jobs":{"new_matches":4,"drafts":2,"active":1,"interview":0,"followup_due":0,
                 "top_new":[{"title":"Data Analyst","company":"PT A"},{"title":"BI","company":"PT B"}]},
         "today":{"items":[{"time":"10:00","title":"Interview PT X","kind":"event"},
                           {"time":null,"title":"Follow-up Y","kind":"followup"}],"calendar":"ok"},
         "queue":{"running":0,"queued":2,"failed":1,
                  "recent":[{"title":"Ringkas","status":"done","model":"ag/gemini-3.8-flash"},
                            {"title":"Draft","status":"queued","model":null}]},
         "vps":{"cpu":13,"ram":49,"disk":23,"down":["site:demo"],"backup_ok":true,
                "load":0.46,"uptime_days":7,"backup_at":"03:00",
                "history":{"cpu":[5,13],"ram":[48,49],"disk":[23,23]}},
         "quota":{"claude":{"accounts":1,"session":57,"weekly":72,"reset":"18:30"},
                  "gemini":{"accounts":11,"session":100,"weekly":92,"reset":"18:56","missing":1},
                  "codex":{"accounts":1,"session":null,"weekly":88,"reset":null}},
         "github":{"user":"Fqih","total":4393,"today":0,"streak":1,"weeks":[[0,1,2,3,4,0,1],[2,0,-1,-1,-1,-1,-1]]},
         "router":{"ag":"10/11","cx":"1/1","gh":"1/1"},
         "level":"warn"}
    """.trimIndent()

    @Test
    fun parsesLiveShape() {
        val s = Status.parse(live)
        assertEquals("warn", s.level)
        assertEquals("2026-10-16T11:18:12+07:00", s.updated)
        assertEquals(Jobs(4, 2, 1, 0, 0, listOf(Match("Data Analyst", "PT A"), Match("BI", "PT B"))), s.jobs)
        assertEquals(listOf(Agenda("10:00", "Interview PT X"), Agenda(null, "Follow-up Y")), s.today!!.items)
        assertEquals("ok", s.today!!.calendar)
        assertEquals(Queue(0, 2, 1, listOf(TaskRow("Ringkas", "done", "ag/gemini-3.8-flash"), TaskRow("Draft", "queued", null))), s.queue)
        assertEquals(Vps(13, 49, 23, listOf("site:demo"), true, 0.46, 7, "03:00",
            History(listOf(5, 13), listOf(48, 49), listOf(23, 23))), s.vps)
        assertEquals(listOf(Quota("gemini", 11, 100, 92, "18:56", missing = 1), Quota("claude", 1, 57, 72, "18:30"),
            Quota("codex", 1, null, 88, null)), s.quota)
        assertEquals(QuotaState.READY, s.quotaState)
        assertEquals(Contrib("Fqih", 4393, 0, 1, listOf(listOf(0, 1, 2, 3, 4, 0, 1), listOf(2, 0, -1, -1, -1, -1, -1))), s.github)
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

    @Test
    fun olderServerWithoutDetailStillParses() {
        val s = Status.parse("""{"level":"ok","jobs":{"new_matches":1},"queue":{"queued":1},"vps":{"cpu":5}}""")
        assertEquals(emptyList<Match>(), s.jobs!!.topNew)
        assertEquals(emptyList<TaskRow>(), s.queue!!.recent)
        assertNull(s.vps!!.load)
        assertNull(s.vps!!.uptimeDays)
        assertNull(s.vps!!.backupAt)
        assertEquals(History(), s.vps!!.history)
        assertEquals(emptyList<Quota>(), s.quota)
        assertEquals(QuotaState.MISSING, s.quotaState)
        assertNull(s.github)
    }

    @Test
    fun quotaStatesAreDistinct() {
        assertEquals(QuotaState.LOADING, Status.parse("""{"quota":{"loading":true}}""").quotaState)
        assertEquals(QuotaState.ERROR, Status.parse("""{"quota":{"error":"HTTPError: 401"}}""").quotaState)
        val empty = Status.parse("""{"quota":{}}""")
        assertEquals(QuotaState.READY, empty.quotaState)
        assertEquals(emptyList<Quota>(), empty.quota)
    }

    @Test(expected = JSONException::class)
    fun rejectsNonJson() {
        Status.parse("<html>login</html>")
    }
}
