# Hub home-screen widget (Android app)

Date: 2026-10-16
Status: approved; look revised 2026-10-16 (frosted glass)

## Goal

Replace the KWGT formula widget with a native Android widget that looks
designed, reads the Hub `/status` JSON over Tailscale, and needs no
per-line setup on the phone. Pushes stay in ntfy; this app only shows state.

Success means:

- One resizable widget on the POCO X6 Pro (HyperOS, Android 14+) shows
  jobs, today's agenda, task queue, VPS health and 9router accounts.
- Setup on the phone is: install the APK, open it once, paste the status
  URL, add the widget.
- The widget refreshes by itself at least every 30 minutes, and on demand
  with a refresh button.
- When the VPS or Tailscale is unreachable, the widget keeps the last data
  and says how old it is.

## Scope

In scope: one Android app with a settings screen and one Glance widget,
build scripts, install instructions. No change to the Hub server: the
existing `/status` JSON is the contract.

Out of scope: notifications (ntfy already does this), writing to the Hub
(enqueue tasks, change job status), Play Store release, iOS, multiple
users.

## Constraints

- Owner-only app, installed from a locally built, locally signed APK.
  The keystore and its passwords stay outside the repository.
- Repository is public: no tailnet IPs, hostnames or tokens in code, tests
  or docs. The status URL (with its token) is entered on the phone and
  stored with Android Keystore encryption.
- Build on the laptop with the installed toolchain: JDK 17, Android SDK
  platform 35/36, build-tools 35/36, Gradle wrapper. No CI.
- `minSdk 31` (Android 12, needed for Material You dynamic color and
  modern widget sizing); `targetSdk 35`.
- hub-status speaks plain HTTP inside the tailnet. Android's network
  security config cannot express an IP range, so it permits cleartext, and
  the app itself enforces the boundary: it only ever requests the one URL
  the owner saved, and refuses to save a URL whose host is not in
  100.64.0.0/10 or under `.ts.net`.

## Design

### Look

Frosted glass (owner's choice, replaces Material You): a ~45% black layer
with a thin light rim over the wallpaper, white text, neutral tiles. App
widgets cannot blur what is behind them, so the look comes from alpha
layers only. Only the status level pill and alarms use color: ok green,
warn amber, crit red.

Glance `SizeMode.Responsive` picks one of three layouts from the height:

| Size | From | Shows |
|---|---|---|
| Small | 140 dp | header, 3 job tiles, Load/RAM/Disk bars, backup line |
| Medium | 330 dp | 5 job tiles, 2 agenda items, quota chips (5 h remaining), VPS bars |
| Large (4x7) | 560 dp | adds 2 newest matches, 3 agenda items, last 3 tasks, quota rows (5 h and 7 day remaining, reset time), 6 h line charts for Load/RAM/Disk with current percent |

From 680 dp the large layout adds a GitHub section: the contribution
squares (white at rising opacity, newest week on the right, as many weeks
as fit) with yearly total, streak and today's count; tapping opens the
profile. The charts grow with any height above that base (560 dp without
GitHub, 680 dp with it), up to 120 dp each, so a taller widget fills with
chart instead of empty space.

GitHub data comes from `/status` `github`, parsed hourly on the VPS from the
public `github.com/users/<user>/contributions` page (no token).
Glance containers hold at most 10 children, so each section is its own
Column.

Quota comes from `/status` `quota` (average remaining percent over active
9router accounts per provider, refreshed every 15 minutes on the VPS).
Chart samples come from `vps.history` (5-minute samples, last 6 hours).

### Tap targets

- Refresh icon: fetch now.
- Jobs cards: open the Telegram jobs bot link saved in settings (optional).
- VPS line and header: open the dashboard (the saved status URL with the
  path `/status` replaced by `/`) in the browser.

### Data flow

1. `StatusRepository.fetch()` does one GET on the saved URL with a 10 s
   timeout, parses JSON with `org.json` (built into Android, no library).
2. The parsed snapshot plus fetch time is stored in the widget's Glance
   state (DataStore preferences), so the widget renders without network.
3. A WorkManager periodic job (every 30 min, network required) and the
   refresh action call fetch, store, then `HubWidget.updateAll()`.
4. On failure the old snapshot stays; an `error` field is set and the
   header shows `offline · 11:18` with the last success time.

A missing section or a section shaped `{"error": "..."}` renders as `–`
for that section only.

### Settings screen

One Compose activity: status URL field (paste), optional jobs bot link,
"Tes koneksi" button that fetches once and shows level + updated time or
the error text, and a save button. Validation: http/https, host inside
100.64.0.0/10 or ending in `.ts.net`, path `/status`, `token` query
parameter present.

### Code layout

```
android-widget/
  settings.gradle.kts, build.gradle.kts, gradle/ (wrapper)
  app/src/main/
    AndroidManifest.xml
    java/.../hub/
      Status.kt          data classes + parse(json) -> Status
      StatusRepository.kt fetch(url) -> Result<Status>
      SettingsStore.kt   encrypted URL + bot link
      UrlRules.kt        validation, dashboard URL from status URL
      HubWidget.kt       Glance widget, small/large layouts
      RefreshWorker.kt   WorkManager job + refresh action
      SettingsActivity.kt
    res/xml/hub_widget_info.xml, network_security_config.xml
  app/src/test/          JVM unit tests: parse, UrlRules, age text
```

Dependencies: AndroidX Glance (appwidget + material3), WorkManager,
Compose Material3 for settings, `androidx.security:security-crypto` or a
small Keystore wrapper for the encrypted URL. No networking library:
`HttpURLConnection` is enough.

### HyperOS

HyperOS restricts background work. The install guide tells the owner to
set the app's battery to "No restrictions" and enable Autostart, and the
refresh button covers missed periodic runs.

## Error handling

| Case | Behaviour |
|---|---|
| Tailscale off / VPS down | keep last data, header `offline · <last time>` |
| 403 (bad token) | header `token salah`, settings screen shows it too |
| Malformed JSON or missing section | that section shows `–` |
| No URL saved yet | widget shows "Buka app untuk setup" and opens settings on tap |
| Periodic job killed by HyperOS | data ages; refresh button still works |

## Testing

- JVM unit tests (JUnit): `Status.parse` on the live JSON shape, on error
  sections and missing keys; `UrlRules` accept/reject cases and dashboard
  URL derivation; relative age text.
- Build check: `./gradlew testDebugUnitTest assembleRelease`.
- Manual on the phone: add widget in both sizes, refresh, airplane mode
  shows offline with old data, tap targets open the right places.
  Screenshot of both sizes goes in the PR, not the repo.

## Delivery

- `android-widget/README.md`: build, sign (keystore path via
  `~/.gradle/gradle.properties`), install with `adb install` over USB or
  wireless debugging, phone setup steps.
- The status URL reaches the phone the same way as before (ntfy message
  from the VPS), so it is never typed.
- `docs/widget.md` points to the app; the KWGT section is removed.
