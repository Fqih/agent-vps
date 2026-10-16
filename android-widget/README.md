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
   from the ntfy message "URL widget Hub" (how to send it: `../docs/widget.md`), then "Tes koneksi", then
   "Simpan".
3. Long-press the home screen, Widgets, Hub, place it, resize to 4x2 or
   4x3+.
4. HyperOS: Settings > Apps > Hub > Battery saver: **No restrictions**,
   and enable **Autostart**, so the 30-minute refresh is not killed.

The ⟳ icon refreshes at once. Header shows the server time of the last
good data; `offline · 11:18` means the last fetch failed and the numbers
are from 11:18.
