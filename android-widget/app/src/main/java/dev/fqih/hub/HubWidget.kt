package dev.fqih.hub

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.LocalSize
import androidx.glance.action.Action
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.color.ColorProvider
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.size
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider as UnitColorProvider
import kotlinx.coroutines.flow.first

class HubWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Responsive(setOf(SMALL, LARGE))

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val store = Store(context)
        val initial = store.snapshot.first()
        provideContent {
            val snap by store.snapshot.collectAsState(initial = initial)
            GlanceTheme { Content(snap, large = LocalSize.current.height >= LARGE.height) }
        }
    }

    companion object {
        val SMALL = DpSize(250.dp, 110.dp)
        val LARGE = DpSize(250.dp, 220.dp)
    }
}

class HubWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = HubWidget()

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        Refresh.schedule(context)
    }
}

// Level colors stay fixed so ok/warn/crit read the same on any wallpaper.
private fun fixed(c: Color): UnitColorProvider = ColorProvider(day = c, night = c)
private val OK = fixed(Color(0xFF43A047))
private val WARN = fixed(Color(0xFFFFB300))
private val CRIT = fixed(Color(0xFFE53935))
private fun levelColor(level: String) = when (level) { "ok" -> OK; "crit" -> CRIT; else -> WARN }

private fun open(url: String): Action = actionStartActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))

@Composable
private fun body(size: Int = 13, bold: Boolean = false, color: UnitColorProvider = GlanceTheme.colors.onSurface) =
    TextStyle(color = color, fontSize = size.sp, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal)

@Composable
private fun Content(snap: Snapshot, large: Boolean) {
    val status = snap.raw?.let { runCatching { Status.parse(it) }.getOrNull() }
    val setup = actionStartActivity<SettingsActivity>()
    val dashboard = snap.url?.let { open(UrlRules.dashboard(it)) } ?: setup
    Column(
        GlanceModifier.fillMaxSize().background(GlanceTheme.colors.widgetBackground)
            .cornerRadius(20.dp).padding(horizontal = 14.dp, vertical = 10.dp)
    ) {
        Header(status, snap, dashboard)
        if (status != null && snap.url != null) {
            Spacer(GlanceModifier.height(8.dp))
            JobCards(status.jobs, snap.bot?.let { open(it) } ?: dashboard)
            Spacer(GlanceModifier.height(8.dp))
            AgendaLines(status.today, if (large) 3 else 1)
            if (large) {
                Spacer(GlanceModifier.height(6.dp))
                Detail(status)
            }
            Spacer(GlanceModifier.defaultWeight())
            VpsBars(status, dashboard)
        } else {
            Spacer(GlanceModifier.defaultWeight())
            Text(
                if (snap.url == null) "Tap untuk tempel Status URL" else "Tekan ⟳ untuk memuat",
                style = body(color = GlanceTheme.colors.onSurfaceVariant),
                modifier = GlanceModifier.clickable(setup),
            )
            Spacer(GlanceModifier.defaultWeight())
        }
    }
}

@Composable
private fun Header(status: Status?, snap: Snapshot, onTap: Action) {
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Row(GlanceModifier.defaultWeight().clickable(onTap), verticalAlignment = Alignment.CenterVertically) {
            Text("Hub", style = body(15, bold = true))
            Spacer(GlanceModifier.width(8.dp))
            if (status != null) {
                Box(GlanceModifier.size(8.dp).cornerRadius(4.dp).background(levelColor(status.level))) {}
                Spacer(GlanceModifier.width(4.dp))
                Text(status.level, style = body(12, color = levelColor(status.level)))
            }
        }
        Text(
            Format.header(status, snap.error, configured = snap.url != null),
            style = body(12, color = GlanceTheme.colors.onSurfaceVariant), maxLines = 1,
        )
        Spacer(GlanceModifier.width(8.dp))
        Image(
            ImageProvider(R.drawable.ic_refresh), contentDescription = "Refresh",
            modifier = GlanceModifier.size(20.dp).clickable(actionRunCallback<RefreshAction>()),
        )
    }
}

@Composable
private fun JobCards(jobs: Jobs?, onTap: Action) {
    Row(GlanceModifier.fillMaxWidth().clickable(onTap)) {
        Card(jobs?.newMatches, "baru")
        Spacer(GlanceModifier.width(6.dp))
        Card(jobs?.active, "aktif")
        Spacer(GlanceModifier.width(6.dp))
        Card(jobs?.interview, "interview")
    }
}

@Composable
private fun androidx.glance.layout.RowScope.Card(value: Int?, label: String) {
    Column(
        GlanceModifier.defaultWeight().background(GlanceTheme.colors.secondaryContainer)
            .cornerRadius(12.dp).padding(vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value?.toString() ?: "–", style = body(18, bold = true, color = GlanceTheme.colors.onSecondaryContainer))
        Text(label, style = body(11, color = GlanceTheme.colors.onSecondaryContainer))
    }
}

@Composable
private fun AgendaLines(today: Today?, max: Int) {
    val items = today?.items.orEmpty()
    if (items.isEmpty()) {
        val text = when (today?.calendar) { null -> "📅 –"; "off" -> "📅 Kalender belum login"; else -> "📅 Agenda kosong" }
        Text(text, style = body(color = GlanceTheme.colors.onSurfaceVariant), maxLines = 1)
        return
    }
    items.take(max).forEach { item ->
        Text("📅 ${item.time ?: "•"}  ${item.title}", style = body(), maxLines = 1)
    }
}

@Composable
private fun Detail(status: Status) {
    val q = status.queue
    val muted = GlanceTheme.colors.onSurfaceVariant
    Text(
        if (q == null) "⚙ –" else "⚙ ${q.running} jalan · ${q.queued} antri · ${q.failed} gagal" +
            (status.jobs?.let { " · FU ${it.followupDue}" } ?: ""),
        style = body(12, color = muted), maxLines = 1,
    )
    Text("🔌 ${Format.router(status.router)}", style = body(12, color = muted), maxLines = 1)
    val down = status.vps?.down.orEmpty()
    if (down.isNotEmpty()) {
        Text("⚠ ${down.joinToString(", ")}", style = body(12, color = levelColor(status.level)), maxLines = 1)
    }
}

@Composable
private fun VpsBars(status: Status, onTap: Action) {
    val v = status.vps
    Row(GlanceModifier.fillMaxWidth().clickable(onTap), verticalAlignment = Alignment.CenterVertically) {
        Bar("CPU", v?.cpu)
        Spacer(GlanceModifier.width(8.dp))
        Bar("RAM", v?.ram)
        Spacer(GlanceModifier.width(8.dp))
        Bar("Disk", v?.disk)
        Spacer(GlanceModifier.width(8.dp))
        Text(
            when (v?.backupOk) { true -> "✓ bkp"; false -> "✗ bkp"; null -> "–" },
            style = body(11, color = if (v?.backupOk == false) CRIT else GlanceTheme.colors.onSurfaceVariant),
        )
    }
}

@Composable
private fun androidx.glance.layout.RowScope.Bar(label: String, percent: Int?) {
    Column(GlanceModifier.defaultWeight()) {
        Text("$label ${percent?.let { "$it%" } ?: "–"}", style = body(10, color = GlanceTheme.colors.onSurfaceVariant))
        LinearProgressIndicator(
            progress = (percent ?: 0) / 100f,
            modifier = GlanceModifier.fillMaxWidth().height(5.dp),
            color = GlanceTheme.colors.primary,
            backgroundColor = GlanceTheme.colors.surfaceVariant,
        )
    }
}
