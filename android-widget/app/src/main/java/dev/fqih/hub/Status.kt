package dev.fqih.hub

import org.json.JSONArray
import org.json.JSONObject

data class Jobs(val newMatches: Int, val active: Int, val interview: Int, val followupDue: Int)
data class Agenda(val time: String?, val title: String)
data class Today(val items: List<Agenda>, val calendar: String)
data class Queue(val running: Int, val queued: Int, val failed: Int)
data class Vps(val cpu: Int, val ram: Int, val disk: Int, val down: List<String>, val backupOk: Boolean)

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
                jobs = o.section("jobs")?.let {
                    Jobs(it.optInt("new_matches"), it.optInt("active"), it.optInt("interview"), it.optInt("followup_due"))
                },
                today = o.section("today")?.let { t ->
                    val items = t.optJSONArray("items").objects().map { e ->
                        Agenda(if (e.isNull("time")) null else e.optString("time"), e.optString("title"))
                    }
                    Today(items, t.optString("calendar", "off"))
                },
                queue = o.section("queue")?.let { Queue(it.optInt("running"), it.optInt("queued"), it.optInt("failed")) },
                vps = o.section("vps")?.let { v ->
                    val down = v.optJSONArray("down")
                    Vps(v.optInt("cpu"), v.optInt("ram"), v.optInt("disk"),
                        (0 until (down?.length() ?: 0)).map { down!!.optString(it) }, v.optBoolean("backup_ok"))
                },
                router = o.section("router")?.let { r -> r.keys().asSequence().associateWith { r.optString(it) } }
                    ?: emptyMap(),
            )
        }

        private fun JSONObject.section(name: String): JSONObject? = optJSONObject(name)?.takeUnless { it.has("error") }

        private fun JSONArray?.objects(): List<JSONObject> =
            if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
    }
}
