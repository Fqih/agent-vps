package dev.fqih.hub

import org.json.JSONArray
import org.json.JSONObject

data class Match(val title: String, val company: String)
data class Jobs(
    val newMatches: Int, val drafts: Int, val active: Int, val interview: Int, val followupDue: Int,
    val topNew: List<Match>,
)
data class Agenda(val time: String?, val title: String)
data class Today(val items: List<Agenda>, val calendar: String)
data class TaskRow(val title: String, val status: String, val model: String?)
data class Queue(val running: Int, val queued: Int, val failed: Int, val recent: List<TaskRow>)
data class Vps(
    val cpu: Int, val ram: Int, val disk: Int, val down: List<String>, val backupOk: Boolean,
    val load: Double?, val uptimeDays: Int?, val backupAt: String?,
)

/** The Hub /status JSON. A section the server reports as {"error": ...} or omits is null. */
data class Status(
    val updated: String?,
    val level: String,
    val jobs: Jobs?,
    val today: Today?,
    val queue: Queue?,
    val vps: Vps?,
    val router: Map<String, String>,
) {
    companion object {
        /** Throws org.json.JSONException when [raw] is not a JSON object. */
        fun parse(raw: String): Status {
            val o = JSONObject(raw)
            return Status(
                updated = o.optString("updated").ifEmpty { null },
                level = o.optString("level", "warn"),
                jobs = o.section("jobs")?.let { j ->
                    Jobs(j.optInt("new_matches"), j.optInt("drafts"), j.optInt("active"), j.optInt("interview"),
                        j.optInt("followup_due"),
                        j.optJSONArray("top_new").objects().map { Match(it.optString("title"), it.optString("company")) })
                },
                today = o.section("today")?.let { t ->
                    val items = t.optJSONArray("items").objects().map { e ->
                        Agenda(if (e.isNull("time")) null else e.optString("time"), e.optString("title"))
                    }
                    Today(items, t.optString("calendar", "off"))
                },
                queue = o.section("queue")?.let { q ->
                    Queue(q.optInt("running"), q.optInt("queued"), q.optInt("failed"),
                        q.optJSONArray("recent").objects().map { TaskRow(it.optString("title"), it.optString("status"), it.text("model")) })
                },
                vps = o.section("vps")?.let { v ->
                    val down = v.optJSONArray("down")
                    Vps(v.optInt("cpu"), v.optInt("ram"), v.optInt("disk"),
                        (0 until (down?.length() ?: 0)).map { down!!.optString(it) }, v.optBoolean("backup_ok"),
                        if (v.has("load") && !v.isNull("load")) v.optDouble("load") else null,
                        if (v.has("uptime_days") && !v.isNull("uptime_days")) v.optInt("uptime_days") else null,
                        v.text("backup_at"))
                },
                router = o.section("router")?.let { r -> r.keys().asSequence().associateWith { r.optString(it) } }
                    ?: emptyMap(),
            )
        }

        /** Absent or JSON null reads as null, not as the string "null". */
        private fun JSONObject.text(name: String): String? = if (isNull(name)) null else optString(name)

        private fun JSONObject.section(name: String): JSONObject? = optJSONObject(name)?.takeUnless { it.has("error") }

        private fun JSONArray?.objects(): List<JSONObject> =
            if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
    }
}
