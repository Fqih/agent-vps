package dev.fqih.hub

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime

/** One calendar instance on the phone; [begin] is epoch millis. */
data class PhoneEvent(val eventId: Long, val title: String, val begin: Long, val allDay: Boolean)

/** Reads today's and tomorrow's events from every calendar synced on the phone and sends them to the Hub. */
object PhoneAgenda {
    fun allowed(context: Context): Boolean =
        context.checkSelfPermission(Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED

    /** Only title and times leave the phone: no location, notes or attendees. */
    fun toJson(events: List<PhoneEvent>, zone: ZoneId): String {
        val items = JSONArray()
        events.forEach { e ->
            val instant = Instant.ofEpochMilli(e.begin)
            // All-day instances are stored at UTC midnight, so their date is the UTC date.
            val date = if (e.allDay) instant.atOffset(ZoneOffset.UTC).toLocalDate() else instant.atZone(zone).toLocalDate()
            items.put(JSONObject()
                .put("id", "${e.eventId}:${e.begin}")
                .put("title", e.title)
                .put("start", if (e.allDay) JSONObject.NULL else instant.atZone(zone).toOffsetDateTime().toString())
                .put("date", date.toString())
                .put("all_day", e.allDay))
        }
        return JSONObject().put("events", items).toString()
    }

    fun read(context: Context, zone: ZoneId = ZoneId.systemDefault()): List<PhoneEvent> {
        val from = LocalDate.now(zone).atStartOfDay(zone)
        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, from.toInstant().toEpochMilli())
            ContentUris.appendId(it, from.plusDays(2).toInstant().toEpochMilli())
        }.build()
        val projection = arrayOf(CalendarContract.Instances.EVENT_ID, CalendarContract.Instances.TITLE,
            CalendarContract.Instances.BEGIN, CalendarContract.Instances.ALL_DAY)
        val out = mutableListOf<PhoneEvent>()
        context.contentResolver.query(uri, projection, null, null, CalendarContract.Instances.BEGIN)?.use { c ->
            while (c.moveToNext() && out.size < 100) {
                out += PhoneEvent(c.getLong(0), c.getString(1).orEmpty(), c.getLong(2), c.getInt(3) == 1)
            }
        }
        return out
    }

    /** Blocking; call off the main thread. Does nothing without the calendar permission. */
    fun push(context: Context, statusUrl: String): Result<Unit> {
        if (!allowed(context)) return Result.success(Unit)
        val json = runCatching { toJson(read(context), ZoneId.systemDefault()) }.getOrElse { return Result.failure(it) }
        return StatusFetcher.post(UrlRules.agenda(statusUrl), json)
    }
}
