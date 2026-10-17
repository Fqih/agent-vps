package dev.fqih.hub

import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SettingsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = Store(applicationContext)
        setContent {
            val ctx = LocalContext.current
            val colors = if (isSystemInDarkTheme()) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)
            MaterialTheme(colorScheme = colors) {
                Surface(Modifier.fillMaxSize()) { SettingsScreen(store) { finish() } }
            }
        }
    }
}

@Composable
private fun SettingsScreen(store: Store, done: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf("") }
    var bot by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    var calendar by remember { mutableStateOf(PhoneAgenda.allowed(context)) }
    val askCalendar = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        calendar = granted
        message = if (granted) "Kalender HP diizinkan; agenda dikirim ke Hub tiap refresh." else "Izin kalender ditolak."
    }
    LaunchedEffect(Unit) {
        url = store.url().orEmpty()
        bot = store.bot().orEmpty()
    }

    fun problem(): String? = UrlRules.problem(url) ?: UrlRules.botProblem(bot)

    Column(
        Modifier.fillMaxSize().safeDrawingPadding().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Hub widget", style = MaterialTheme.typography.headlineSmall)
        Text("Tempel STATUS URL dari notifikasi ntfy \"URL widget Hub\".", style = MaterialTheme.typography.bodyMedium)
        OutlinedTextField(
            value = url, onValueChange = { url = it }, label = { Text("Status URL") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(onClick = {
            val clip = (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).primaryClip
            clip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(context)?.let { url = it.toString().trim() }
        }) { Text("Tempel dari clipboard") }
        OutlinedTextField(
            value = bot, onValueChange = { bot = it }, label = { Text("Link bot jobs (opsional, https://t.me/...)") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(onClick = { askCalendar.launch(Manifest.permission.READ_CALENDAR) }, enabled = !calendar) {
            Text(if (calendar) "Kalender HP: aktif" else "Izinkan kalender HP")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = {
                val bad = problem()
                if (bad != null) {
                    message = bad
                } else {
                    message = "Menghubungi…"
                    scope.launch {
                        val result = withContext(Dispatchers.IO) { StatusFetcher.fetch(url.trim()) }
                        message = result.fold(
                            { raw -> Status.parse(raw).let { "Terhubung · ${it.level} · ${Format.clock(it.updated)}" } },
                            { "Gagal: ${it.message}" },
                        )
                    }
                }
            }) { Text("Tes koneksi") }
            Button(onClick = {
                val bad = problem()
                if (bad != null) {
                    message = bad
                } else {
                    scope.launch {
                        store.saveSettings(url, bot)
                        Refresh.schedule(context)
                        Refresh.run(context)
                        done()
                    }
                }
            }) { Text("Simpan") }
        }
        message?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
    }
}
