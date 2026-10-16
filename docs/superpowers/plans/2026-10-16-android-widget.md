# Hub Android Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native Android app with one resizable Material You home-screen widget that shows the Hub `/status` JSON over Tailscale.

**Architecture:** Pure-Kotlin core (`Status`, `Format`, `UrlRules`, `StatusFetcher`) tested on the JVM; Android shell (`Vault` for Keystore encryption, `Store` on DataStore, `Refresh` + WorkManager, Glance `HubWidget`, Compose `SettingsActivity`) verified by build and on the phone. The Hub server is unchanged.

**Tech Stack:** Kotlin 2.3.20, AGP 8.13.1, Gradle 8.14 wrapper, compileSdk 36 / targetSdk 35 / minSdk 31, Jetpack Glance 1.2.0, WorkManager 2.12.0, DataStore 1.2.1, Compose BOM 2026.09.00, JUnit 4.13.2, org.json 20260814 (tests only).

**Spec:** `docs/superpowers/specs/2026-10-16-android-widget-design.md`

## Global Constraints

- Public repository: no tailnet IPs, hostnames or tokens in code, tests or docs. Test fixtures use `100.64.0.1` and `box.example.ts.net`.
- The status URL is stored encrypted with an Android Keystore AES-GCM key; `android:allowBackup="false"`.
- The app only requests the one saved URL, and refuses to save a URL whose host is not in 100.64.0.0/10 or under `.ts.net`, whose path is not `/status`, or that has no non-empty `token` query parameter.
- Error text shown in the widget never contains the URL or token.
- No networking or JSON library in the app: `HttpURLConnection` and Android's `org.json`.
- Keystore file and passwords live outside the repo (`~/.gradle/gradle.properties`); `*.jks` is git-ignored.
- UI text is Indonesian.
- Every command below runs from `android-widget/` unless it says otherwise. `ANDROID_HOME=/home/faqihhakim/Android/Sdk` is already exported.

## Review Focus

- A section shaped `{"error": "..."}`, a missing section, or a `null` agenda time must render `–` or be skipped, never crash the widget (StatusTest covers parse; HubWidget must not use `!!` on sections).
- Long agenda titles or many down checks must not push the VPS bars off the widget (`maxLines = 1` on every text, down list joined into one line).
- A Keystore key lost after reinstall or a corrupted blob must lead to the "Buka app untuk setup" state, not a crash (`runCatching` around `Vault.decrypt`).
- 9router keys come from a `JSONObject`, whose key order is not stable; the router line must be sorted (`FormatTest.routerSorted`).
- Fetch failure messages are fixed strings and never echo the URL (`StatusFetcherTest.errorHidesToken`).

---

### Task 1: Project scaffold that builds

**Files:**
- Create: `android-widget/settings.gradle.kts`, `android-widget/build.gradle.kts`, `android-widget/gradle.properties`, `android-widget/.gitignore`
- Create: `android-widget/app/build.gradle.kts`
- Create: `android-widget/app/src/main/AndroidManifest.xml`
- Create: `android-widget/app/src/main/res/values/strings.xml`
- Create: `android-widget/app/src/main/res/drawable/ic_hub_fg.xml`, `android-widget/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`, `android-widget/app/src/main/res/values/colors.xml`
- Create: `android-widget/app/src/main/java/dev/fqih/hub/SettingsActivity.kt` (placeholder, replaced in Task 7)
- Generate: Gradle wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/*`)

**Interfaces:**
- Produces: Gradle module `:app`, package `dev.fqih.hub`, `./gradlew assembleDebug` and `./gradlew testDebugUnitTest` working.

- [ ] **Step 1: Write the build files**

`android-widget/settings.gradle.kts`:
```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "hub-widget"
include(":app")
```

`android-widget/build.gradle.kts`:
```kotlin
plugins {
    id("com.android.application") version "8.13.1" apply false
    id("org.jetbrains.kotlin.android") version "2.3.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.20" apply false
}
```

`android-widget/gradle.properties`:
```properties
org.gradle.jvmargs=-Xmx2g
android.useAndroidX=true
kotlin.code.style=official
```

`android-widget/.gitignore`:
```
.gradle/
build/
local.properties
*.jks
*.keystore
.idea/
```

`android-widget/app/build.gradle.kts`:
```kotlin
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "dev.fqih.hub"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.fqih.hub"
        minSdk = 31
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    signingConfigs {
        create("release") {
            // Keystore lives outside the repo: set these in ~/.gradle/gradle.properties.
            findProperty("hubStoreFile")?.let { storeFile = file(it as String) }
            storePassword = findProperty("hubStorePassword") as String?
            keyAlias = findProperty("hubKeyAlias") as String?
            keyPassword = findProperty("hubKeyPassword") as String?
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.glance:glance-appwidget:1.2.0")
    implementation("androidx.glance:glance-material3:1.2.0")
    implementation("androidx.work:work-runtime-ktx:2.12.0")
    implementation("androidx.datastore:datastore-preferences:1.2.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20260814") // android.jar's org.json is a stub on the JVM
}
```

- [ ] **Step 2: Write the manifest, resources and placeholder activity**

`android-widget/app/src/main/AndroidManifest.xml` (receiver and network config are added in Tasks 6 and 7):
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:theme="@android:style/Theme.Material.NoActionBar">

        <activity
            android:name=".SettingsActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

`android-widget/app/src/main/res/values/strings.xml`:
```xml
<resources>
    <string name="app_name">Hub</string>
    <string name="widget_description">Status Hub: jobs, agenda, antrian, VPS</string>
</resources>
```

`android-widget/app/src/main/res/values/colors.xml`:
```xml
<resources>
    <color name="ic_launcher_background">#1E3A5F</color>
</resources>
```

`android-widget/app/src/main/res/drawable/ic_hub_fg.xml` (three stacked bars, a status-board glyph):
```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp"
    android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#FFFFFF" android:pathData="M34,38h40a4,4 0,0 1,4 4v0a4,4 0,0 1,-4 4h-40a4,4 0,0 1,-4 -4v0a4,4 0,0 1,4 -4z" />
    <path android:fillColor="#9BE7A0" android:pathData="M34,52h28a4,4 0,0 1,4 4v0a4,4 0,0 1,-4 4h-28a4,4 0,0 1,-4 -4v0a4,4 0,0 1,4 -4z" />
    <path android:fillColor="#FFD54F" android:pathData="M34,66h16a4,4 0,0 1,4 4v0a4,4 0,0 1,-4 4h-16a4,4 0,0 1,-4 -4v0a4,4 0,0 1,4 -4z" />
</vector>
```

`android-widget/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_hub_fg" />
</adaptive-icon>
```

`android-widget/app/src/main/java/dev/fqih/hub/SettingsActivity.kt`:
```kotlin
package dev.fqih.hub

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Text

class SettingsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { Text("Hub") }
    }
}
```

- [ ] **Step 3: Generate the Gradle wrapper with the cached Gradle 8.14**

Run: `~/.gradle/wrapper/dists/gradle-8.14-bin/2ec11z2vggy155in4nrvsdmtc/gradle-8.14/bin/gradle wrapper --gradle-version 8.14 --distribution-type bin`
Expected: `BUILD SUCCESSFUL`; `gradlew` and `gradle/wrapper/gradle-wrapper.properties` exist.

- [ ] **Step 4: Build**

Run: `./gradlew assembleDebug testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`; `app/build/outputs/apk/debug/app-debug.apk` exists. If a version pair is rejected (for example Compose BOM needing a newer Kotlin), bump the smallest number that the error names, re-run, and record it as a ruling.

- [ ] **Step 5: Commit**

```bash
git add android-widget
git commit -m "feat(widget): scaffold android hub widget project"
```

---

### Task 2: Status model and display text

**Files:**
- Create: `android-widget/app/src/main/java/dev/fqih/hub/Status.kt`
- Create: `android-widget/app/src/main/java/dev/fqih/hub/Format.kt`
- Test: `android-widget/app/src/test/java/dev/fqih/hub/StatusTest.kt`, `android-widget/app/src/test/java/dev/fqih/hub/FormatTest.kt`

**Interfaces:**
- Produces:
  - `data class Jobs(newMatches: Int, active: Int, interview: Int, followupDue: Int)`
  - `data class Agenda(time: String?, title: String)`
  - `data class Today(items: List<Agenda>, calendar: String)`
  - `data class Queue(running: Int, queued: Int, failed: Int)`
  - `data class Vps(cpu: Int, ram: Int, disk: Int, down: List<String>, backupOk: Boolean)`
  - `data class Status(updated: String?, level: String, jobs: Jobs?, today: Today?, queue: Queue?, vps: Vps?, router: Map<String, String>)` with `Status.parse(raw: String): Status` (throws `org.json.JSONException`)
  - `object Format { fun clock(iso: String?): String; fun header(status: Status?, error: String?, configured: Boolean): String; fun router(map: Map<String, String>): String }`

- [ ] **Step 1: Write the failing tests**

`StatusTest.kt`:
```kotlin
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
```

`FormatTest.kt`:
```kotlin
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./gradlew testDebugUnitTest`
Expected: FAIL, compilation errors `Unresolved reference 'Status'` / `'Format'`.

- [ ] **Step 3: Write the implementation**

`Status.kt`:
```kotlin
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
```

`Format.kt`:
```kotlin
package dev.fqih.hub

object Format {
    /** "2026-10-16T11:18:12+07:00" -> "11:18"; the server already sends WIB. */
    fun clock(iso: String?): String =
        iso?.takeIf { it.length >= 16 && it[13] == ':' }?.substring(11, 16) ?: "--:--"

    /** Header right side: setup hint, loading, error, or the server time with the error in front. */
    fun header(status: Status?, error: String?, configured: Boolean): String = when {
        !configured -> "Buka app untuk setup"
        status == null -> error ?: "Memuat…"
        error != null -> "$error · ${clock(status.updated)}"
        else -> clock(status.updated)
    }

    fun router(map: Map<String, String>): String =
        if (map.isEmpty()) "–" else map.toSortedMap().entries.joinToString(" · ") { "${it.key} ${it.value}" }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./gradlew testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, StatusTest 3/3 and FormatTest 3/3 pass.

- [ ] **Step 5: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): parse hub status and format widget text"
```

---

### Task 3: URL rules

**Files:**
- Create: `android-widget/app/src/main/java/dev/fqih/hub/UrlRules.kt`
- Test: `android-widget/app/src/test/java/dev/fqih/hub/UrlRulesTest.kt`

**Interfaces:**
- Produces: `object UrlRules { fun problem(raw: String): String?; fun isTailnet(host: String): Boolean; fun dashboard(statusUrl: String): String; fun botProblem(raw: String): String? }`

- [ ] **Step 1: Write the failing test**

```kotlin
package dev.fqih.hub

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class UrlRulesTest {
    @Test
    fun acceptsTailnetStatusUrls() {
        assertNull(UrlRules.problem("http://100.64.0.1:8090/status?token=abc"))
        assertNull(UrlRules.problem("  http://box.example.ts.net:8090/status?token=abc  "))
        assertNull(UrlRules.problem("https://100.127.255.254/status?x=1&token=abc"))
    }

    @Test
    fun rejectsEverythingElse() {
        listOf(
            "http://192.168.1.2:8090/status?token=abc",
            "http://8.8.8.8/status?token=abc",
            "http://100.128.0.1/status?token=abc",
            "http://example.com/status?token=abc",
            "ftp://100.64.0.1/status?token=abc",
            "http://100.64.0.1:8090/?token=abc",
            "http://100.64.0.1:8090/status",
            "http://100.64.0.1:8090/status?token=",
            "not a url",
            "",
        ).forEach { assertNotNull(it, UrlRules.problem(it)) }
    }

    @Test
    fun dashboardKeepsToken() {
        assertEquals("http://100.64.0.1:8090/?token=abc", UrlRules.dashboard(" http://100.64.0.1:8090/status?token=abc"))
    }

    @Test
    fun botLinkOptionalButHttps() {
        assertNull(UrlRules.botProblem(""))
        assertNull(UrlRules.botProblem("https://t.me/some_bot"))
        assertNotNull(UrlRules.botProblem("http://t.me/some_bot"))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew testDebugUnitTest --tests dev.fqih.hub.UrlRulesTest`
Expected: FAIL, `Unresolved reference 'UrlRules'`.

- [ ] **Step 3: Write the implementation**

```kotlin
package dev.fqih.hub

import java.net.URI

/** The app only ever talks to a Hub status URL inside the tailnet. */
object UrlRules {
    /** Null when [raw] is usable, otherwise the reason shown in settings. */
    fun problem(raw: String): String? {
        val uri = runCatching { URI(raw.trim()) }.getOrNull() ?: return "URL tidak valid"
        if (uri.scheme !in setOf("http", "https")) return "Harus diawali http:// atau https://"
        val host = uri.host ?: return "URL tidak valid"
        if (!isTailnet(host)) return "Host harus alamat Tailscale (100.x.x.x atau .ts.net)"
        if (uri.path != "/status") return "Path harus /status"
        val hasToken = uri.rawQuery?.split("&")?.any { it.startsWith("token=") && it.length > "token=".length } == true
        return if (hasToken) null else "Token belum ada di URL"
    }

    /** 100.64.0.0/10 (Tailscale CGNAT range) or a MagicDNS name. */
    fun isTailnet(host: String): Boolean {
        if (host.endsWith(".ts.net")) return true
        val parts = host.split(".").map { it.toIntOrNull() ?: return false }
        return parts.size == 4 && parts.all { it in 0..255 } && parts[0] == 100 && parts[1] in 64..127
    }

    /** hub-status serves the dashboard at / with the same token. Call only on a URL that passed [problem]. */
    fun dashboard(statusUrl: String): String = statusUrl.trim().replaceFirst("/status?", "/?")

    fun botProblem(raw: String): String? =
        if (raw.isBlank() || raw.trim().startsWith("https://")) null else "Link bot harus https://"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./gradlew testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, all tests pass (Status 3, Format 3, UrlRules 4).

- [ ] **Step 5: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): restrict status url to the tailnet"
```

---

### Task 4: Status fetcher

**Files:**
- Create: `android-widget/app/src/main/java/dev/fqih/hub/StatusFetcher.kt`
- Test: `android-widget/app/src/test/java/dev/fqih/hub/StatusFetcherTest.kt`

**Interfaces:**
- Consumes: `Status.parse(raw)` (Task 2).
- Produces: `object StatusFetcher { fun fetch(url: String, timeoutMs: Int = 10_000): Result<String> }` returning the raw JSON that parsed successfully; failures carry `FetchError` with message `"token salah"`, `"HTTP <code>"`, `"data rusak"` or `"offline"`. `class FetchError(message: String) : Exception(message)`.

- [ ] **Step 1: Write the failing test**

```kotlin
package dev.fqih.hub

import com.sun.net.httpserver.HttpServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import java.net.InetSocketAddress

class StatusFetcherTest {
    private var server: HttpServer? = null

    private fun serve(code: Int, body: String): String {
        val s = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        s.createContext("/status") { ex ->
            val bytes = body.toByteArray()
            ex.sendResponseHeaders(code, bytes.size.toLong())
            ex.responseBody.use { it.write(bytes) }
        }
        s.start()
        server = s
        return "http://127.0.0.1:${s.address.port}/status?token=rahasia"
    }

    @After
    fun stop() {
        server?.stop(0)
    }

    private fun message(r: Result<String>) = r.exceptionOrNull()?.message

    @Test
    fun okReturnsRawJson() {
        val r = StatusFetcher.fetch(serve(200, """{"level":"ok"}"""))
        assertEquals("""{"level":"ok"}""", r.getOrNull())
    }

    @Test
    fun forbiddenMeansBadToken() {
        assertEquals("token salah", message(StatusFetcher.fetch(serve(403, "forbidden"))))
    }

    @Test
    fun otherStatusShowsCode() {
        assertEquals("HTTP 500", message(StatusFetcher.fetch(serve(500, "boom"))))
    }

    @Test
    fun nonJsonIsBrokenData() {
        assertEquals("data rusak", message(StatusFetcher.fetch(serve(200, "<html>"))))
    }

    @Test
    fun unreachableIsOffline() {
        val url = serve(200, "{}")
        server!!.stop(0)
        server = null
        assertEquals("offline", message(StatusFetcher.fetch(url, timeoutMs = 2_000)))
    }

    @Test
    fun errorHidesToken() {
        val url = serve(200, "{}")
        server!!.stop(0)
        server = null
        assertFalse(message(StatusFetcher.fetch(url, timeoutMs = 2_000))!!.contains("rahasia"))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./gradlew testDebugUnitTest --tests dev.fqih.hub.StatusFetcherTest`
Expected: FAIL, `Unresolved reference 'StatusFetcher'`.

- [ ] **Step 3: Write the implementation**

```kotlin
package dev.fqih.hub

import org.json.JSONException
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Short, fixed messages: they go straight into the widget header and must never contain the URL. */
class FetchError(message: String) : Exception(message)

object StatusFetcher {
    /** One blocking GET; call it off the main thread. Success carries JSON that Status.parse accepts. */
    fun fetch(url: String, timeoutMs: Int = 10_000): Result<String> = try {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        try {
            when (val code = conn.responseCode) {
                200 -> {
                    val body = conn.inputStream.bufferedReader().use { it.readText() }
                    Status.parse(body)
                    Result.success(body)
                }
                403 -> Result.failure(FetchError("token salah"))
                else -> Result.failure(FetchError("HTTP $code"))
            }
        } finally {
            conn.disconnect()
        }
    } catch (e: JSONException) {
        Result.failure(FetchError("data rusak"))
    } catch (e: IOException) {
        Result.failure(FetchError("offline"))
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./gradlew testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, all tests pass (16 total).

- [ ] **Step 5: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): fetch hub status with short error messages"
```

---

### Task 5: Encrypted settings, snapshot store and refresh scheduling

**Files:**
- Create: `android-widget/app/src/main/java/dev/fqih/hub/Vault.kt`
- Create: `android-widget/app/src/main/java/dev/fqih/hub/Store.kt`
- Create: `android-widget/app/src/main/java/dev/fqih/hub/Refresh.kt`

**Interfaces:**
- Consumes: `StatusFetcher.fetch` (Task 4).
- Produces:
  - `object Vault { fun encrypt(plain: String): String; fun decrypt(blob: String): String }`
  - `data class Snapshot(raw: String?, error: String?, url: String?, bot: String?)`
  - `class Store(context: Context) { val snapshot: Flow<Snapshot>; suspend fun url(): String?; suspend fun bot(): String?; suspend fun saveSettings(url: String, bot: String); suspend fun saveFetch(result: Result<String>) }`
  - `object Refresh { suspend fun run(context: Context); fun schedule(context: Context) }`, `class RefreshWorker : CoroutineWorker`, `class RefreshAction : ActionCallback`
  - Task 6 must define `class HubWidget : GlanceAppWidget()`; `Refresh.run` calls `HubWidget().updateAll(context)`.

These classes need Android Keystore, DataStore and WorkManager, so they are checked by compiling here and on the phone in Task 8. Keep logic out of them: everything testable lives in Tasks 2–4.

- [ ] **Step 1: Write `Vault.kt`**

```kotlin
package dev.fqih.hub

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** AES-GCM with a non-exportable Android Keystore key; the blob is base64(iv || ciphertext). */
object Vault {
    private const val ALIAS = "hub-status-url"
    private const val IV_BYTES = 12

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return gen.generateKey()
    }

    fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        return Base64.encodeToString(cipher.iv + cipher.doFinal(plain.toByteArray()), Base64.NO_WRAP)
    }

    fun decrypt(blob: String): String {
        val bytes = Base64.decode(blob, Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, IV_BYTES))
        return String(cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES))
    }
}
```

- [ ] **Step 2: Write `Store.kt`**

```kotlin
package dev.fqih.hub

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.hubStore by preferencesDataStore("hub")

/** Everything the widget needs to draw without network. [url] is decrypted; null means not set up. */
data class Snapshot(val raw: String?, val error: String?, val url: String?, val bot: String?)

class Store(private val context: Context) {
    private object Keys {
        val url = stringPreferencesKey("url_enc")
        val bot = stringPreferencesKey("bot")
        val raw = stringPreferencesKey("raw")
        val error = stringPreferencesKey("error")
    }

    // A key lost on reinstall or a damaged blob reads as "not set up", never as a crash.
    private fun Preferences.decryptedUrl(): String? = this[Keys.url]?.let { runCatching { Vault.decrypt(it) }.getOrNull() }

    val snapshot: Flow<Snapshot> =
        context.hubStore.data.map { Snapshot(it[Keys.raw], it[Keys.error], it.decryptedUrl(), it[Keys.bot]) }

    suspend fun url(): String? = context.hubStore.data.first().decryptedUrl()

    suspend fun bot(): String? = context.hubStore.data.first()[Keys.bot]

    suspend fun saveSettings(url: String, bot: String) {
        context.hubStore.edit { p ->
            p[Keys.url] = Vault.encrypt(url.trim())
            if (bot.isBlank()) p.remove(Keys.bot) else p[Keys.bot] = bot.trim()
            p.remove(Keys.raw) // data from a previous URL must not show under the new one
            p.remove(Keys.error)
        }
    }

    suspend fun saveFetch(result: Result<String>) {
        context.hubStore.edit { p ->
            result.onSuccess { p[Keys.raw] = it; p.remove(Keys.error) }
                .onFailure { p[Keys.error] = it.message ?: "offline" }
        }
    }
}
```

- [ ] **Step 3: Write `Refresh.kt`**

```kotlin
package dev.fqih.hub

import android.content.Context
import androidx.glance.GlanceId
import androidx.glance.action.ActionParameters
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.updateAll
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

object Refresh {
    /** Fetch once, keep the old data on failure, redraw every widget. */
    suspend fun run(context: Context) {
        val store = Store(context)
        val url = store.url() ?: return
        store.saveFetch(withContext(Dispatchers.IO) { StatusFetcher.fetch(url) })
        HubWidget().updateAll(context)
    }

    fun schedule(context: Context) {
        val request = PeriodicWorkRequestBuilder<RefreshWorker>(30, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork("hub-refresh", ExistingPeriodicWorkPolicy.KEEP, request)
    }
}

class RefreshWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Refresh.run(applicationContext)
        return Result.success()
    }
}

/** The ⟳ button: runs without a network constraint so "offline" shows at once when Tailscale is off. */
class RefreshAction : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        Refresh.run(context)
    }
}
```

- [ ] **Step 4: Add a minimal `HubWidget` so the project compiles, then build**

Create `android-widget/app/src/main/java/dev/fqih/hub/HubWidget.kt` (Task 6 replaces the body):
```kotlin
package dev.fqih.hub

import android.content.Context
import androidx.glance.GlanceId
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.provideContent
import androidx.glance.text.Text

class HubWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent { Text("Hub") }
    }
}
```

Run: `./gradlew assembleDebug testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): store encrypted url and refresh status in background"
```

---

### Task 6: The widget

**Files:**
- Modify: `android-widget/app/src/main/java/dev/fqih/hub/HubWidget.kt` (replace)
- Create: `android-widget/app/src/main/res/xml/hub_widget_info.xml`
- Create: `android-widget/app/src/main/res/drawable/ic_refresh.xml`
- Modify: `android-widget/app/src/main/AndroidManifest.xml` (add receiver)

**Interfaces:**
- Consumes: `Store.snapshot`, `Snapshot` (Task 5); `Status.parse`, `Format` (Task 2); `UrlRules.dashboard` (Task 3); `RefreshAction`, `Refresh.schedule` (Task 5); `SettingsActivity` (Task 1, real in Task 7).
- Produces: `class HubWidget : GlanceAppWidget`, `class HubWidgetReceiver : GlanceAppWidgetReceiver`.

- [ ] **Step 1: Write `HubWidget.kt`**

```kotlin
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
```

Glance API names in this file follow Glance 1.2.0. If the compiler rejects one (for example `ColorProvider` moved between `androidx.glance.color` and `androidx.glance.unit`, or `defaultWeight` needs the `ColumnScope`/`RowScope` receiver), use the name the error suggests and record a ruling; do not change the layout.

- [ ] **Step 2: Write the widget resources**

`android-widget/app/src/main/res/xml/hub_widget_info.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<appwidget-provider xmlns:android="http://schemas.android.com/apk/res/android"
    android:description="@string/widget_description"
    android:initialLayout="@layout/glance_default_loading_layout"
    android:minWidth="250dp"
    android:minHeight="110dp"
    android:minResizeWidth="200dp"
    android:minResizeHeight="110dp"
    android:resizeMode="horizontal|vertical"
    android:targetCellWidth="4"
    android:targetCellHeight="2"
    android:updatePeriodMillis="0"
    android:widgetCategory="home_screen" />
```

`android-widget/app/src/main/res/drawable/ic_refresh.xml`:
```xml
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24"
    android:tint="?android:attr/textColorSecondary">
    <path android:fillColor="#FFFFFF"
        android:pathData="M17.65,6.35A7.96,7.96 0,0 0,12 4a8,8 0,1 0,7.75 10h-2.08A6,6 0,1 1,12 6c1.66,0 3.14,0.69 4.22,1.78L13,11h7V4l-2.35,2.35z" />
</vector>
```

- [ ] **Step 3: Register the receiver in `AndroidManifest.xml`**

Add inside `<application>`, after the activity:
```xml
        <receiver
            android:name=".HubWidgetReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data
                android:name="android.appwidget.provider"
                android:resource="@xml/hub_widget_info" />
        </receiver>
```

- [ ] **Step 4: Build**

Run: `./gradlew assembleDebug testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): draw responsive material you hub widget"
```

---

### Task 7: Settings screen and cleartext config

**Files:**
- Modify: `android-widget/app/src/main/java/dev/fqih/hub/SettingsActivity.kt` (replace)
- Create: `android-widget/app/src/main/res/xml/network_security_config.xml`
- Modify: `android-widget/app/src/main/AndroidManifest.xml` (add `android:networkSecurityConfig`)

**Interfaces:**
- Consumes: `Store`, `Refresh` (Task 5); `UrlRules` (Task 3); `StatusFetcher` (Task 4); `Status.parse`, `Format.clock` (Task 2).

- [ ] **Step 1: Write `SettingsActivity.kt`**

```kotlin
package dev.fqih.hub

import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
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
        Text("Tempel STATUS URL dari notifikasi ntfy \"URL widget\".", style = MaterialTheme.typography.bodyMedium)
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
```

- [ ] **Step 2: Write the network security config and reference it**

`android-widget/app/src/main/res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- hub-status is plain HTTP inside the tailnet. The config cannot express 100.64.0.0/10,
     so cleartext is allowed here and UrlRules restricts which URL may ever be saved. -->
<network-security-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
```

In `AndroidManifest.xml`, add to the `<application>` attributes:
```xml
        android:networkSecurityConfig="@xml/network_security_config"
```

- [ ] **Step 3: Build**

Run: `./gradlew assembleDebug testDebugUnitTest`
Expected: `BUILD SUCCESSFUL`, 16 tests pass.

- [ ] **Step 4: Commit**

```bash
git add android-widget/app/src
git commit -m "feat(widget): add settings screen with connection test"
```

---

### Task 8: Release build, docs and phone install

**Files:**
- Create: `android-widget/README.md`
- Modify: `docs/widget.md` (replace KWGT guide)
- Modify: `README.md` (Hub section: point to the app)

**Interfaces:**
- Consumes: the whole app.

- [ ] **Step 1: Create the keystore outside the repo (owner secret, never committed)**

Run (from the repo root; prompts for nothing because passwords come from the generated file):
```bash
mkdir -p ~/.android-keys && chmod 700 ~/.android-keys
PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
keytool -genkeypair -v -keystore ~/.android-keys/hub-widget.jks -alias hub -keyalg RSA -keysize 4096 \
  -validity 10000 -storepass "$PASS" -keypass "$PASS" -dname "CN=Fqih"
chmod 600 ~/.android-keys/hub-widget.jks
grep -q '^hubStoreFile=' ~/.gradle/gradle.properties 2>/dev/null || cat >> ~/.gradle/gradle.properties <<EOF
hubStoreFile=$HOME/.android-keys/hub-widget.jks
hubStorePassword=$PASS
hubKeyAlias=hub
hubKeyPassword=$PASS
EOF
chmod 600 ~/.gradle/gradle.properties
```
Expected: `~/.android-keys/hub-widget.jks` exists; `~/.gradle/gradle.properties` has the four `hub*` keys. Never print `$PASS`.

- [ ] **Step 2: Build the signed release**

Run: `./gradlew testDebugUnitTest assembleRelease`
Expected: `BUILD SUCCESSFUL`; `app/build/outputs/apk/release/app-release.apk` exists.
Verify: `$ANDROID_HOME/build-tools/36.0.0/apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk | head -2` prints `CN=Fqih`.

- [ ] **Step 3: Write `android-widget/README.md`**

```markdown
# Hub widget (Android)

Home-screen widget for the Hub `/status` JSON, reached over Tailscale.
Design: `../docs/superpowers/specs/2026-10-16-android-widget-design.md`.

## Build

Needs JDK 17 and the Android SDK (`ANDROID_HOME`). The release keystore
lives outside the repo; its path and passwords go in
`~/.gradle/gradle.properties` as `hubStoreFile`, `hubStorePassword`,
`hubKeyAlias`, `hubKeyPassword`.

    ./gradlew testDebugUnitTest assembleRelease

APK: `app/build/outputs/apk/release/app-release.apk`.

## Install on the phone

Either `adb install -r app-release.apk` (USB debugging or wireless
debugging), or send the APK to yourself and open it with "Install unknown
apps" allowed for that app.

## Phone setup

1. Tailscale: connected; if split tunneling is on, include **Hub**.
2. Open **Hub**, tap "Tempel dari clipboard" after copying the STATUS URL
   from the ntfy message "URL widget KWGT", then "Tes koneksi", then
   "Simpan".
3. Long-press the home screen, Widgets, Hub, place it, resize to 4x2 or
   4x3+.
4. HyperOS: Settings > Apps > Hub > Battery saver: **No restrictions**,
   and enable **Autostart**, so the 30-minute refresh is not killed.

The ⟳ icon refreshes at once. Header shows the server time of the last
good data; `offline · 11:18` means the last fetch failed and the numbers
are from 11:18.
```

- [ ] **Step 4: Replace `docs/widget.md`**

```markdown
# Phone widget

The Hub widget is a native Android app in `android-widget/`. Build,
install and phone setup: `android-widget/README.md`.

The widget reads `/status?token=<STATUS_TOKEN>` from hub-status over
Tailscale every 30 minutes and on the ⟳ button. To get the URL onto the
phone without typing the token, publish it once from the VPS to the
`tasks` topic and copy it from the ntfy notification.
```

In the root `README.md` Hub section, replace any sentence that tells the reader to build the KWGT widget with: `Phone widget: see docs/widget.md (native app in android-widget/).`

- [ ] **Step 5: Commit**

```bash
git add android-widget/README.md docs/widget.md README.md
git commit -m "docs(widget): document app build, install and phone setup"
```

- [ ] **Step 6: Deliver the APK to the phone (owner confirms)**

Ask the owner how to deliver: (a) `adb` (owner enables wireless debugging and runs `! adb pair <ip>:<port>` themselves, then `adb install -r app/build/outputs/apk/release/app-release.apk`), or (b) through the Telegram info bot. For (b), write the sender to the session scratchpad (not the repo) as `send_apk.py`:

```python
import json
import sys
import urllib.request
import uuid

from digest import load_env

env = load_env()
boundary = uuid.uuid4().hex
apk = open(sys.argv[1], "rb").read()
head = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{env['TELEGRAM_CHAT_ID']}\r\n"
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"hub-widget.apk\"\r\n"
    "Content-Type: application/vnd.android.package-archive\r\n\r\n"
).encode()
body = head + apk + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendDocument", body,
    {"Content-Type": f"multipart/form-data; boundary={boundary}"},
)
print(json.load(urllib.request.urlopen(req, timeout=60))["ok"])
```

Run (from `android-widget/`, `SCRATCH` = session scratchpad):
```bash
scp app/build/outputs/apk/release/app-release.apk agent-vps:/tmp/hub-widget.apk
scp "$SCRATCH/send_apk.py" agent-vps:/tmp/send_apk.py
ssh agent-vps 'cd ~/hermes_automation && PYTHONPATH=. python3 /tmp/send_apk.py /tmp/hub-widget.apk; rm /tmp/send_apk.py /tmp/hub-widget.apk'
```
Expected: `True`; the APK arrives in the info bot chat.

- [ ] **Step 7: Manual acceptance on the phone (owner)**

Checklist, each observed on the phone:
- Settings: a non-tailnet URL shows "Host harus alamat Tailscale…"; the real URL shows "Terhubung · warn · HH:mm".
- Widget at 4x2 shows header, 3 job cards, one agenda line, CPU/RAM/Disk bars.
- Resized to 4x3+, it adds queue, 9router line and the down list.
- ⟳ updates the header time.
- Tailscale off then ⟳: header shows `offline · HH:mm`, numbers stay.
- Tap job cards opens the bot link (or dashboard when unset); tap header or VPS bars opens the dashboard.
```
