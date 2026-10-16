# Hub design (sub-project 0)

Date: 2026-10-16
Status: draft, waiting for owner review

## Goal

Keep the idle LLM quota on 9router doing useful work around the clock, and
put the information the owner acts on in front of them on the phone without
opening Telegram. The Hub is the shared base for the later sub-projects
(job-application agent, coding assistant, personal assistant).

Success means:

- A home-screen widget shows job pipeline, today's agenda, task queue and
  VPS health, refreshed at least every 15 minutes over Tailscale.
- Important events arrive as ntfy push notifications on the phone.
- Any script or bot can enqueue an LLM task, and a 24/7 worker finishes it
  through 9router with fallback and retry, then notifies the owner.
- Google Calendar events show in the widget and can be created by tasks.

## Scope

In scope: `notify`, `status` (JSON + dashboard), `tasks` + `worker`,
collectors for the widget, Google OAuth helper, Calendar connector, ntfy
server, KWGT widget file, systemd units, monitor checks.

Out of scope (later sub-projects): Gmail, Drive, portal scraping, CV and
cover letter generation (sub-project 1); GitHub (sub-project 2); chat with
memory (sub-project 3). Telegram stays the place for commands and chat.

## Constraints

- VPS: Ubuntu 20.04, Python 3.8, 1 vCPU, 2 GiB RAM (about 1 GiB free).
  Code must run on Python 3.8: no `tomllib`, no `match`, keep
  `from __future__ import annotations`.
- Follow the existing style in this repo: stdlib only, SQLite, systemd
  units, small modules, pytest tests. No new Python dependencies.
- Nothing new is exposed on the public interface. Services bind to
  `127.0.0.1` and are published to the tailnet with `tailscale serve`,
  the same way 9router is.
- No secrets, emails or detailed application content in `/status`.

## Model policy

Model chains live in `hub/models.json`, not in code, so a model that starts
working (or dies) is a one-line change. Antigravity Claude 4.6 models are
not used. Current chains:

| Chain | Order |
|---|---|
| `fast` | `ag/gemini-3.8-flash-high`, `ag/gemini-3.8-flash`, `cx/gpt-6-luna` |
| `heavy` | `ag/gemini-3.1-pro-high`, `ag/gemini-3.8-flash-high`, `cc/claude-sonnet-5-5`, `cx/gpt-6.1-sol` |

`ag/gemini-3.1-pro-high` returns 404 today. The worker remembers a model
that answered 404 and skips it for 6 hours, so a dead head of the chain
costs one slow call, not one per task.

## Architecture

```
hermes_automation/
  hub/
    notify.py       publish(topic, title, message, priority, click=None, tags=None)
    tasks.py        enqueue(kind, payload, chain="fast", dedup_key=None) and queue queries
    worker.py       long-running loop: claim, run handler, retry, notify
    handlers.py     registry kind -> function; ships with "llm.prompt"
    llm.py          chat(chain, messages) over 9router with fallback and the 404 cache
    status.py       HTTP server: /status (JSON), / (dashboard HTML)
    collectors/
      jobs.py       tracker counts from state.sqlite (read-only)
      today.py      calendar events today + tracker follow-ups due
      queue.py      counts from tasks.sqlite
      vps.py        load, RAM, disk, containers, last backup, monitor checks
      router9.py    active account count per provider from the 9router DB (read-only)
    models.json
  connectors/
    google_auth.py  OAuth token load/refresh, one-time consent helper
    gcal.py         list_events(day), create_event(summary, start, end, description)
  widget/
    hub.kwgt        KWGT preset reading /status
```

Data flow:

1. A timer or bot calls `tasks.enqueue(...)`.
2. `worker.py` claims the oldest queued task, runs its handler (usually
   `llm.chat` through 9router), stores the result, and calls `notify.publish`.
3. KWGT fetches `/status`. `status.py` builds it from the collectors, caching
   each collector for 60 seconds.
4. ntfy delivers pushes to the phone app over Tailscale.

### notify

- Publishes to the self-hosted ntfy server with a publisher token from
  `~/.hermes/hermes.env` (`NTFY_URL`, `NTFY_TOKEN`).
- Topics: `alerts` (high), `jobs` (default), `digest` (low, silent).
- Priority mapping follows the agreed table: high = VPS/container down,
  backup failed, interview within 1 hour; default = artifact ready,
  follow-up due, task finished; low = morning summary, weekly recap.
- Never raises. On failure it logs, and for high priority it falls back to
  the Telegram info bot through `tg.send`.

### tasks and worker

`tasks.sqlite` is a separate file from `state.sqlite` to avoid the
`database is locked` failure seen on 2026-10-10. WAL mode, timeout 30.

```sql
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,          -- JSON
  chain TEXT NOT NULL DEFAULT 'fast',
  dedup_key TEXT UNIQUE,
  status TEXT NOT NULL,           -- queued | running | done | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  run_after TEXT NOT NULL,        -- UTC ISO time
  started_at TEXT,
  finished_at TEXT,
  model TEXT,                     -- model that produced the result
  result TEXT,
  error TEXT,
  created_at TEXT NOT NULL
);
```

- `enqueue` with an existing `dedup_key` returns the existing id.
- The worker runs one task at a time (1 vCPU, and quota is the limit, not
  CPU). It polls every 5 seconds when idle.
- Retry: when every model in the chain fails, `attempts += 1` and
  `run_after` moves by 1, 5, then 30 minutes. After the third failure the
  task becomes `failed` and a default-priority notification is sent.
- On start, tasks stuck in `running` for more than 15 minutes go back to
  `queued`.
- First handler, `llm.prompt`: payload `{prompt, title, notify}`; the result
  is sent through ntfy with a link to the dashboard task page. The info bot
  gets a `/tugas <prompt>` command that enqueues it, so the queue is useful
  from day one.

### status

- Stdlib `http.server` (threading) on `127.0.0.1:8090`, published with
  `tailscale serve --tcp 8090`.
- Requires `?token=` (`STATUS_TOKEN` in `hermes.env`) because KWGT can only
  send a URL. Tailnet-only plus token.
- `/status` JSON shape:

```json
{
  "updated": "2026-10-16T09:41:00+07:00",
  "level": "ok",
  "jobs":   {"new_matches": 3, "drafts": 0, "active": 12, "interview": 1, "followup_due": 2},
  "today":  [{"time": "10:00", "title": "Interview PT X", "kind": "event"},
             {"time": null, "title": "Follow-up Deloitte", "kind": "followup"}],
  "queue":  {"running": 1, "queued": 5, "failed": 0},
  "vps":    {"cpu": 23, "ram": 61, "disk": 22, "containers_down": [], "backup_ok": true},
  "router": {"ag": "10/10", "cx": "ok", "cc": "ok"}
}
```

- `level` is the worst of: any container down or backup failed = `crit`;
  disk above 85%, RAM above 90%, a failed task, or Google login broken =
  `warn`; otherwise `ok`.
- A collector that raises puts `{"error": "..."}` in its own section; the
  rest of the response is unaffected.
- `drafts` stays 0 until sub-project 1 fills it.
- `/` renders the same data as a small HTML page with the queue (last 20
  tasks, result preview) and per-check detail. `/task/<id>` shows one result.

### Google connectors

- One OAuth client in the owner's own GCP project, reused later for the
  rclone client-id TODO. Publishing status must be "In production" so the
  refresh token does not expire after 7 days.
- Scope for the Hub: `https://www.googleapis.com/auth/calendar.events`.
  Later sub-projects add `gmail.readonly` and `drive.file` with a fresh
  consent.
- Consent runs once on the laptop (`python -m connectors.google_auth
  login`, loopback redirect), then the token file is copied to
  `~/.hermes/google-token.json` (mode 600) on the VPS.
- Plain REST over `urllib`; refresh the access token when it is within
  5 minutes of expiry.
- On `invalid_grant`, `today` reports an error, `level` becomes `warn`, and
  one notification per day asks for a new login.

### ntfy server

- Docker image `binwiederhier/ntfy`, `127.0.0.1:8091`, published with
  `tailscale serve --tcp 8091`, cache and auth DB in `~/ntfy/`.
- `auth-default-access: deny-all`; one publisher token for the Hub and one
  read token for the phone.
- Added to `monitor.py` `CONTAINERS` and to the daily backup.

### Widget

- `widget/hub.kwgt` lays out the four rows agreed with the owner: jobs,
  today, queue, VPS + 9router, plus the update time. KWGT refresh every
  15 minutes; tapping the jobs row opens the jobs bot, tapping the VPS row
  opens the dashboard.
- Importing a custom preset likely needs KWGT Pro.
- If `/status` is unreachable the widget keeps the last values and shows
  the old update time.

### Morning summary

Existing `infobot` scheduler adds a 07:05 low-priority ntfy message: today's
events, follow-ups due, new matches from the digest. No new timer.

## Error handling summary

| Case | Behaviour |
|---|---|
| Model fails (404/429/5xx) | Next model in the chain; 404 cached for 6 h |
| Whole chain fails | Retry after 1, 5, 30 min, then `failed` + notify |
| Worker crash | systemd `Restart=always`; stale `running` tasks requeued |
| Duplicate work | `dedup_key` |
| ntfy down | Log; Telegram fallback for high priority only |
| Google token broken | Widget warning, one notice per day, rest keeps working |
| Collector error | Section-level error, `/status` still answers |
| Hub service down | `monitor.py` checks `hub-worker` and `hub-status`; healthchecks.io covers the whole VPS |

## Deployment

- systemd units: `hub-worker.service`, `hub-status.service` (both
  `Restart=always`, `MemoryMax=150M`).
- New env keys in `hermes.env`: `NTFY_URL`, `NTFY_TOKEN`, `STATUS_TOKEN`.
- `tailscale serve --tcp 8090` and `--tcp 8091` (owner runs these, since
  they change tailnet exposure).
- Phone setup: ntfy app (subscribe to the three topics with the read
  token, battery unrestricted), KWGT + preset, Tailscale always-on with the
  split-tunnel app list (Termux, ntfy, KWGT, browser).

## Testing

- Unit (pytest, same style as `test_infobot.py`): enqueue + dedup, claim
  order and `run_after`, retry schedule, stale task recovery, 404 cache,
  `level` rules, collector error isolation, notify fallback, Google token
  refresh and `invalid_grant`, `gcal` request/response with mocked HTTP.
- Integration: worker against a local fake 9router (`http.server`) that
  fails the first model and answers the second.
- Smoke after deploy: test push reaches the phone, `curl /status` from the
  laptop over Tailscale, one `llm.prompt` task end to end.
- Coverage target 80% for `hub/` and `connectors/`.
