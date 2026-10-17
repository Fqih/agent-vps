package dev.fqih.hub

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.ColorFilter
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.Image
import androidx.glance.ImageProvider
import androidx.glance.LocalContext
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
import androidx.glance.layout.ContentScale
import androidx.glance.layout.ColumnScope
import androidx.glance.layout.Row
import androidx.glance.layout.RowScope
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
    // Exact, not Responsive: Responsive reports the matched breakpoint as LocalSize, so the layout
    // could never see the real 4x7 height that unlocks GitHub and taller charts.
    override val sizeMode = SizeMode.Exact

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val store = Store(context)
        val initial = store.snapshot.first()
        provideContent {
            val snap by store.snapshot.collectAsState(initial = initial)
            Content(snap, Layout.of(LocalSize.current.height.value))
        }
    }
}

class HubWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = HubWidget()

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        Refresh.schedule(context)
    }
}


// Frosted glass: neutral translucent layers over the wallpaper, white text. App widgets cannot blur
// what is behind them, so the look comes from alpha only; colors are fixed and ignore Material You.
private fun fixed(c: Long): UnitColorProvider = ColorProvider(day = Color(c), night = Color(c))
private val GLASS = fixed(0x73000000)   // ~45% black
private val EDGE = fixed(0x26FFFFFF)    // thin light rim
private val TILE = fixed(0x1FFFFFFF)
private val LINE = fixed(0x1AFFFFFF)
private val TEXT = fixed(0xFFFFFFFF)
private val MUTED = fixed(0xB3FFFFFF)
private val FAINT = fixed(0x80FFFFFF)
private val BAR = fixed(0xE6FFFFFF)
private val OK = fixed(0xFF66BB6A)
private val WARN = fixed(0xFFFFCA28)
private val CRIT = fixed(0xFFEF5350)
private fun levelColor(level: String) = when (level) { "ok" -> OK; "crit" -> CRIT; else -> WARN }

private fun open(url: String): Action = actionStartActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))

private fun style(size: Int = 12, bold: Boolean = false, color: UnitColorProvider = TEXT) =
    TextStyle(color = color, fontSize = size.sp, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal)

@Composable
private fun Content(snap: Snapshot, layout: Layout) {
    val status = snap.raw?.let { runCatching { Status.parse(it) }.getOrNull() }
    val setup = actionStartActivity<SettingsActivity>()
    val dashboard = snap.url?.let { open(UrlRules.dashboard(it)) } ?: setup
    Box(GlanceModifier.fillMaxSize().background(EDGE).cornerRadius(24.dp).padding(1.dp)) {
        Column(GlanceModifier.fillMaxSize().background(GLASS).cornerRadius(23.dp).padding(horizontal = 14.dp, vertical = 12.dp)) {
            Header(status, snap, dashboard)
            if (status != null && snap.url != null) {
                Body(status, layout.size, layout.chart, layout.github, snap.bot?.let { open(it) } ?: dashboard, dashboard)
            } else {
                Spacer(GlanceModifier.defaultWeight())
                Text(
                    if (snap.url == null) "Tap untuk tempel Status URL" else "Tekan ⟳ untuk memuat",
                    style = style(13, color = MUTED), modifier = GlanceModifier.clickable(setup),
                )
                Spacer(GlanceModifier.defaultWeight())
            }
        }
    }
}

@Composable
private fun ColumnScope.Body(status: Status, size: Size, chart: Int, github: Boolean, jobsTap: Action, dashboard: Action) {
    // Glance containers hold at most 10 children, so every section is its own Column.
    // Heights: SMALL ~130 dp, MEDIUM ~300 dp, LARGE ~520 dp (+ ~115 dp GitHub) plus the chart height.
    Jobs(status.jobs, size, jobsTap)
    if (size != Size.SMALL) Agenda(status.today, if (size == Size.LARGE) 3 else 2)
    if (size == Size.LARGE) Tasks(status.queue)
    if (size != Size.SMALL) QuotaSection(status, detail = size == Size.LARGE)
    if (github) GitHub(status.github)
    Spacer(GlanceModifier.defaultWeight())
    if (size == Size.LARGE) VpsCharts(status, chart, dashboard) else Vps(status, size, dashboard)
}

@Composable
private fun Header(status: Status?, snap: Snapshot, onTap: Action) {
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Row(GlanceModifier.defaultWeight().clickable(onTap), verticalAlignment = Alignment.CenterVertically) {
            Text("HUB", style = style(15, bold = true))
            Spacer(GlanceModifier.width(8.dp))
            if (status != null) {
                Box(GlanceModifier.background(levelColor(status.level)).cornerRadius(8.dp).padding(horizontal = 7.dp, vertical = 1.dp)) {
                    Text(status.level.uppercase(), style = style(10, bold = true, color = fixed(0xFF000000)))
                }
            }
        }
        Text(Format.header(status, snap.error, configured = snap.url != null), style = style(11, color = MUTED), maxLines = 1)
        Spacer(GlanceModifier.width(8.dp))
        Image(
            ImageProvider(R.drawable.ic_refresh), contentDescription = "Refresh",
            colorFilter = ColorFilter.tint(TEXT),
            modifier = GlanceModifier.size(20.dp).clickable(actionRunCallback<RefreshAction>()),
        )
    }
}

@Composable
private fun Section(title: String, trailing: String = "", titled: Boolean = true, content: @Composable ColumnScope.() -> Unit) {
    if (!titled) {
        Column(GlanceModifier.fillMaxWidth().padding(top = 8.dp), content = content)
        return
    }
    Column(GlanceModifier.fillMaxWidth()) {
        Spacer(GlanceModifier.height(8.dp))
        Box(GlanceModifier.fillMaxWidth().height(1.dp).background(LINE)) {}
        Spacer(GlanceModifier.height(6.dp))
        Row(GlanceModifier.fillMaxWidth()) {
            Text(title, style = style(10, bold = true, color = FAINT), modifier = GlanceModifier.defaultWeight())
            if (trailing.isNotEmpty()) Text(trailing, style = style(10, color = MUTED), maxLines = 1)
        }
        Spacer(GlanceModifier.height(4.dp))
        Column(GlanceModifier.fillMaxWidth(), content = content) // own container: keeps each Column under 10 children
    }
}

@Composable
private fun Jobs(jobs: Jobs?, size: Size, onTap: Action) {
    Section("JOBS", titled = size != Size.SMALL) {
        Row(GlanceModifier.fillMaxWidth().clickable(onTap)) {
            Tile(jobs?.newMatches, "baru")
            Gap()
            if (size != Size.SMALL) {
                Tile(jobs?.drafts, "draft")
                Gap()
            }
            Tile(jobs?.active, "aktif")
            Gap()
            Tile(jobs?.interview, "intv")
            if (size != Size.SMALL) {
                Gap()
                Tile(jobs?.followupDue, "FU")
            }
        }
        if (size == Size.LARGE) {
            jobs?.topNew.orEmpty().take(2).forEach { m ->
                Spacer(GlanceModifier.height(3.dp))
                Row(GlanceModifier.fillMaxWidth().clickable(onTap)) {
                    Text("•  ", style = style(12, color = FAINT))
                    Text(m.title, style = style(12), maxLines = 1, modifier = GlanceModifier.defaultWeight())
                    Text("  ${m.company}", style = style(11, color = MUTED), maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun RowScope.Gap() = Spacer(GlanceModifier.width(6.dp))

@Composable
private fun RowScope.Tile(value: Int?, label: String) {
    Column(
        GlanceModifier.defaultWeight().background(TILE).cornerRadius(12.dp).padding(vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(value?.toString() ?: "–", style = style(17, bold = true))
        Text(label, style = style(10, color = MUTED))
    }
}

@Composable
private fun Agenda(today: Today?, max: Int) {
    Section("AGENDA HARI INI") {
        val items = today?.items.orEmpty()
        if (items.isEmpty()) {
            val text = when (today?.calendar) { null -> "–"; "off" -> "Kalender belum login"; else -> "Agenda kosong" }
            Text(text, style = style(12, color = MUTED), maxLines = 1)
        } else {
            items.take(max).forEach { item ->
                Row(GlanceModifier.fillMaxWidth().padding(vertical = 1.dp)) {
                    Text(item.time ?: "•", style = style(12, bold = true), modifier = GlanceModifier.width(44.dp))
                    Text(item.title, style = style(12), maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun Tasks(queue: Queue?) {
    val counts = if (queue == null) "–" else "${queue.running} jalan · ${queue.queued} antri · ${queue.failed} gagal"
    Section("TASK", counts) {
        val rows = queue?.recent.orEmpty()
        if (rows.isEmpty()) {
            Text("Belum ada task", style = style(12, color = MUTED))
        }
        rows.take(3).forEach { t ->
            Row(GlanceModifier.fillMaxWidth().padding(vertical = 1.dp)) {
                Text(Format.taskIcon(t.status), style = style(12, color = if (t.status == "failed") CRIT else MUTED),
                    modifier = GlanceModifier.width(18.dp))
                Text(t.title, style = style(12), maxLines = 1, modifier = GlanceModifier.defaultWeight())
                Text("  ${Format.model(t.model)}", style = style(10, color = FAINT), maxLines = 1)
            }
        }
    }
}

@Composable
private fun Vps(status: Status, size: Size, onTap: Action) {
    val v = status.vps
    Section("VPS", backupText(v), titled = size != Size.SMALL) {
        Row(GlanceModifier.fillMaxWidth().clickable(onTap), verticalAlignment = Alignment.CenterVertically) {
            Bar("Load", v?.cpu)
            Spacer(GlanceModifier.width(10.dp))
            Bar("RAM", v?.ram)
            Spacer(GlanceModifier.width(10.dp))
            Bar("Disk", v?.disk)
        }
        if (size == Size.SMALL) {
            Spacer(GlanceModifier.height(4.dp))
            Text(backupText(v), style = style(10, color = if (v?.backupOk == false) CRIT else MUTED), maxLines = 1)
        }
        Down(status)
    }
}

private fun backupText(v: Vps?) = when (v?.backupOk) {
    true -> "✓ backup ${v.backupAt ?: ""}".trim()
    false -> "✗ backup gagal"
    null -> "backup –"
}

@Composable
private fun Down(status: Status) {
    val down = status.vps?.down.orEmpty()
    if (down.isNotEmpty()) {
        Text("⚠ ${down.joinToString(", ")}", style = style(11, color = levelColor(status.level)), maxLines = 1)
    }
}

@Composable
private fun VpsCharts(status: Status, chartDp: Int, onTap: Action) {
    val v = status.vps
    val density = LocalContext.current.resources.displayMetrics.density
    val widthDp = ((LocalSize.current.width.value - 28 - 20) / 3).coerceAtLeast(40f)
    Section("VPS · 6 JAM", Format.vpsSummary(v?.uptimeDays, v?.load)) {
        Row(GlanceModifier.fillMaxWidth().clickable(onTap)) {
            ChartCell("Load", v?.cpu, v?.history?.cpu.orEmpty(), widthDp, chartDp, density)
            Spacer(GlanceModifier.width(10.dp))
            ChartCell("RAM", v?.ram, v?.history?.ram.orEmpty(), widthDp, chartDp, density)
            Spacer(GlanceModifier.width(10.dp))
            ChartCell("Disk", v?.disk, v?.history?.disk.orEmpty(), widthDp, chartDp, density)
        }
        Spacer(GlanceModifier.height(5.dp))
        Text(backupText(v), style = style(11, color = if (v?.backupOk == false) CRIT else MUTED), maxLines = 1)
        Down(status)
    }
}

@Composable
private fun RowScope.ChartCell(label: String, percent: Int?, samples: List<Int>, widthDp: Float, heightDp: Int, density: Float) {
    val hot = (percent ?: 0) >= 90
    val bitmap = Chart.bitmap(samples, (widthDp * density).toInt(), (heightDp * density).toInt(),
        if (hot) 0xFFEF5350.toInt() else 0xE6FFFFFF.toInt())
    Column(GlanceModifier.defaultWeight()) {
        Row(GlanceModifier.fillMaxWidth()) {
            Text(label, style = style(10, color = MUTED), modifier = GlanceModifier.defaultWeight())
            Text(percent?.let { "$it%" } ?: "–", style = style(12, bold = true, color = if (hot) CRIT else TEXT))
        }
        Spacer(GlanceModifier.height(3.dp))
        Image(ImageProvider(bitmap), contentDescription = "$label 6 jam", contentScale = ContentScale.FillBounds,
            modifier = GlanceModifier.fillMaxWidth().height(heightDp.dp).background(TILE).cornerRadius(8.dp))
    }
}

@Composable
private fun RowScope.Bar(label: String, percent: Int?, alarm: Boolean = (percent ?: 0) >= 90) {
    Column(GlanceModifier.defaultWeight()) {
        Row(GlanceModifier.fillMaxWidth()) {
            Text(label, style = style(10, color = MUTED), modifier = GlanceModifier.defaultWeight())
            Text(percent?.let { "$it%" } ?: "–", style = style(10, bold = true))
        }
        Spacer(GlanceModifier.height(3.dp))
        LinearProgressIndicator(
            progress = (percent ?: 0) / 100f,
            modifier = GlanceModifier.fillMaxWidth().height(5.dp).cornerRadius(3.dp),
            color = if (alarm) CRIT else BAR,
            backgroundColor = TILE,
        )
    }
}

@Composable
private fun QuotaSection(status: Status, detail: Boolean) {
    val quota = status.quota
    Section("KUOTA 9ROUTER", if (detail) "sisa 5 jam · 7 hari" else "sisa 5 jam") {
        if (quota.isEmpty()) {
            val text = when (status.quotaState) {
                QuotaState.LOADING -> "memuat…"; QuotaState.ERROR -> "– kuota error"
                QuotaState.READY -> "tidak ada akun"; QuotaState.MISSING -> "–"
            }
            Text(text, style = style(12, color = MUTED))
        } else if (detail) {
            quota.forEach { q -> QuotaRow(q) }
        } else {
            // Three weighted two-line chips share the ~222 dp content width, so the percent never clips.
            Row(GlanceModifier.fillMaxWidth()) {
                quota.forEachIndexed { i, q ->
                    if (i > 0) Spacer(GlanceModifier.width(6.dp))
                    Column(
                        GlanceModifier.defaultWeight().background(TILE).cornerRadius(8.dp).padding(horizontal = 4.dp, vertical = 3.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(Format.provider(q), style = style(9, color = MUTED), maxLines = 1)
                        Text(q.session?.let { "$it%" } ?: "–", style = style(12, bold = true), maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun GitHub(c: Contrib?) {
    val density = LocalContext.current.resources.displayMetrics.density
    val widthPx = ((LocalSize.current.width.value - 28) * density).toInt()
    val cell = (10 * density).toInt()
    val gap = (2 * density).toInt().coerceAtLeast(1)
    Section("GITHUB${c?.user?.let { " · $it" } ?: ""}", c?.let { Format.github(it) } ?: "") {
        if (c == null) {
            Text("–", style = style(12, color = MUTED))
        } else {
            Image(ImageProvider(Grid.bitmap(c.weeks, widthPx, cell, gap)), contentDescription = "Kontribusi GitHub",
                contentScale = ContentScale.FillBounds,
                modifier = GlanceModifier.fillMaxWidth().height((7 * 10 + 6 * 2).dp)
                    .clickable(open("https://github.com/${c.user}")))
        }
    }
}

@Composable
private fun QuotaRow(q: Quota) {
    Row(GlanceModifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(Format.quotaName(q), style = style(12, bold = true), maxLines = 1, modifier = GlanceModifier.width(64.dp))
        Bar("5 jam", q.session, alarm = (q.session ?: 100) <= 10)
        Spacer(GlanceModifier.width(8.dp))
        Bar("7 hari", q.weekly, alarm = (q.weekly ?: 100) <= 10)
        Text(q.reset?.let { "  ↻$it" } ?: "", style = style(10, color = FAINT), maxLines = 1)
    }
}
