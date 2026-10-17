# Widget quota and VPS charts

Date: 2026-10-16
Spec: `docs/superpowers/specs/2026-10-16-android-widget-design.md` (Look section)
Status: implemented on `feat/widget-app` (commits 6613c31..39cbe45); this
plan records the design for independent review. Accepted findings become
follow-up commits.

## Goal

The large (4x7) widget had empty space below the task list. The owner asked
for: remaining quota per 9router provider (average Gemini over all accounts,
Claude, Codex) as real percentages, and Load/RAM/Disk as line charts with the
current percent. Medium and small layouts must stop clipping.

## Acceptance criteria

1. `/status` has `quota`: `{"gemini"|"claude"|"codex": {"accounts", "session",
   "weekly", "reset"}}`, where session/weekly are the average remaining
   percent over active accounts and reset is the soonest session reset in
   WIB `HH:MM`.
2. `/status` stays fast (under 1 s) even though fetching usage for 13
   accounts takes about 60 s.
3. `/status` `vps.history` has `cpu`, `ram`, `disk` lists, oldest first,
   5-minute samples over the last 6 hours, at most 36 points.
4. A broken 9router dashboard, a slow account, or a failing VPS sample
   (the new code in this change) does not break `/status` or the infobot
   schedule.
5. Widget large layout shows quota rows (5 h and 7 day bars, reset time) and
   three line charts with current percent; charts grow with extra height.
   Medium shows quota chips; small shows tiles, bars and the backup line.
6. No secret (dashboard password, cookie, token) appears in code, tests,
   logs, `/status` or docs. The repository is public.

## Approach

### Server (Python 3.8, stdlib only)

- `hub/quota.py`
  - `summarize(usages)` pure: maps 9router provider bodies to the summary.
    Key per provider: antigravity `gemini_session`/`gemini_weekly`, claude
    `session (5h)`/`weekly (7d)`, codex `session`/`weekly`. Percent is
    `remainingPercentage`, else `remaining/total`, else `(total-used)/total`;
    `unlimited` counts as 100. Each account body and each quota entry is
    validated on its own: a non-object body or `quotas`, a non-numeric
    percent, or an unparsable `resetAt` reads as null for that value only, so
    one malformed account never aborts the provider or the whole summary.
    A `resetAt` without a timezone offset counts as unparsable (null); valid
    values are converted to UTC before taking the soonest, then shown in WIB.
  - `fetch(ctx)`: reads active connection rows from the 9router SQLite DB
    (read-only URI) and keeps only eligible rows, whose provider is in
    `PROVIDERS` (antigravity, claude, codex); other providers such as github
    are ignored. Zero eligible rows returns `{}` immediately, without login.
    Otherwise it logs in with `POST /api/auth/login` using
    `ROUTER_DASHBOARD_PASSWORD` from `~/.hermes/hermes.env` into an in-memory
    cookie jar, then `GET /api/usage/<id>` per eligible account (30 s
    timeout, a failing account is logged and skipped). If eligible rows
    exist but not one usage request succeeded, `fetch` raises, so
    `refresh_once` keeps the last good value and records the error.
  - A daemon thread started in `hub.status.main` runs `refresh_once` every
    15 minutes. `collect` returns the last good value, `{"error": ...}` if no
    refresh ever succeeded, or `{}` before the first refresh finishes.
  - Accepted cost: `/status` shows `{}` for about a minute after a restart,
    and the 60 s collector cache can hold that `{}` for one more minute.
- `hub/history.py`: table `vps_samples(ts TEXT PRIMARY KEY, cpu, ram, disk)`
  in `state.sqlite`. `record` inserts and prunes rows older than 24 h;
  `series(db, now, hours=6, points=36)` thins evenly, keeps first and last.
  A missing table reads as empty lists.
- `infobot.scheduled`: inside the existing 5-minute check block, call
  `hub.collectors.vps.collect` and `history.record`, wrapped in
  try/except so it cannot stop the schedule. infobot owns the writable
  `state.sqlite` connection; hub-status only opens it read-only.
- `hub/collectors/vps.py` adds `history` from `series` using its existing
  read-only connection.

### Widget (Kotlin, Glance 1.2)

- `Status.kt`: `History(cpu, ram, disk)` on `Vps` (default empty), and
  `quota: List<Quota>` in fixed order gemini, claude, codex; JSON null
  session/weekly/reset read as null. A quota section shaped `{"error": ...}`
  sets `quotaError = true` (other error sections stay null as before), so
  the widget can tell "loading" (`{}`) from "failed" (error).
- `Chart.kt`: pure `points(values, width, height)` (oldest at x=0, 100% at
  top, clamp 0..100, one sample draws a flat line, none draws nothing) and
  `bitmap(...)` drawing line plus translucent fill with
  `android.graphics.Canvas`, shown via `ImageProvider(Bitmap)` because Glance
  has no canvas.
- `HubWidget.kt`: thresholds SMALL 110 dp, MEDIUM 330 dp, LARGE 560 dp
  (estimated content heights about 130, 300 and 520 dp + chart). Chart height
  is `40 + (height - 560)` clamped to 40..120 dp. The 9ROUTER account-count
  section is replaced by the quota section. CPU is labeled "Load" because the
  value is load average over cores. Quota bars turn red at 10% remaining or
  less; usage bars turn red at 90% or more.
- Quota states in the widget: empty `{}` shows `memuat…`; error shows
  `–` with `kuota error` in muted text.
- Medium quota chips: one Row, three chips each `defaultWeight()`, 6 dp
  gaps, chip padding 4 dp horizontal and 3 dp vertical. Each chip is a
  centered Column of two lines: provider name (9 sp, muted, `maxLines = 1`)
  and remaining session percent (12 sp bold). At 250 dp width the content
  is ~222 dp, a chip ~70 dp, text room ~62 dp; "Gemini" at 9 sp is ~30 dp
  and "100%" at 12 sp bold ~30 dp, so both lines fit and the percent is
  always on its own line. The account count is not shown in chips.

## Non-goals

Hardening `monitor.run_checks` (`/proc/meminfo` read before the check
block; pre-existing behaviour, unchanged here; the scheduler loop already
logs and retries it), per-account quota detail, quota alerts, charts on the small/medium layouts,
history longer than 6 h in the widget, Glance UI tests.

## Risks

- Widget bitmaps count toward the RemoteViews bitmap limit (screen width x
  height x 4 bytes x 1.5, about 19.8 MB on the 1220x2712 POCO X6 Pro). Worst
  case at a full-width 4x7 widget: chart cell ~100x120 dp at density 2.75 is
  275x330 px ARGB_8888 = ~363 KB, three charts ~1.1 MB, well under the
  limit. Bitmaps need alpha, so RGB_565 is not an option.
- Height estimates are by hand; real launcher cell sizes on HyperOS are not
  measured. Overflow clips at the bottom (VPS section).
- The 9router usage API is undocumented and may change shape; summarize then
  returns null percentages instead of crashing.

## Tests added for the review findings

- `test_hub_quota`: `quotas: null` body and a bad `resetAt` next to a good
  account still summarize the good one; a timezone-less `resetAt` next to a
  `Z` one is ignored, not a crash, and the reset comes from the `Z` value;
  all eligible usage requests failing keeps the last value (fetch raises);
  zero eligible rows returns `{}` without a login request; a DB whose only
  active provider is github returns `{}` without a login request.
- `StatusTest`: quota `{"error": ...}` gives empty list and
  `quotaError = true`; `{}` gives empty list and `quotaError = false`.
- `FormatTest`: chip label has no account count.

## Verification

- Server: `cd agent-vps && python3 -m unittest test_filters test_infobot
  test_hub_notify test_hub_tasks test_hub_llm test_hub_worker test_google
  test_hub_collectors test_hub_status test_hub_morning test_hub_wiring
  test_backup test_env_example test_hub_quota test_hub_history` → 124 OK.
- Android: `cd agent-vps/android-widget && ./gradlew testDebugUnitTest
  assembleRelease` → 26 tests pass, release APK builds.
- Live: `/status` on the VPS returns `quota` with 3 providers and
  `vps.history` lists (checked after deploy).
- Manual on the phone: 4x7, 4x4 and 4x2 render without clipping; charts show
  a line after a few samples.

## Review outcome (2026-10-17)

Codex reviewed this plan for 5 rounds without APPROVED. Accepted findings
Q-1, Q-2, W-1, W-2, WIDGET-1, MEM-1, R3-1/R4-1, R3-2/R4-2 and R5-1 are
implemented: `collect` returns `{"loading": true}` before the first refresh,
`{}` after a successful refresh with no eligible accounts, and the widget
maps these to `memuat…`, `tidak ada akun` and `– kuota error`
(`QuotaState`). SCHED-1 stays a non-goal. The owner then added the GitHub
contribution grid (see the spec), which no review round covered.
