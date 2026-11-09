"""Morning push text and the 'interview in 1 hour' check, used by infobot's scheduler."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta

from hub import filler, tasks
from hub.collectors import jobs, today
from hub.collectors.common import WIB


def morning_text(ctx: dict, now: datetime) -> str:
    agenda = today.collect(ctx, now)["items"]
    counts = jobs.collect(ctx, now)
    lines = [f"{item['time']} {item['title']}" if item["time"] else item["title"] for item in agenda]
    lines = lines or ["Tidak ada agenda hari ini."]
    lines.append(f"{counts['new_matches']} lowongan baru · {counts['active']} aktif · "
                 f"{counts['followup_due']} follow-up jatuh tempo")
    if ctx.get("tasks_db"):
        with closing(tasks.connect(ctx["tasks_db"])) as db:
            done = filler.summary(db, now - timedelta(days=1))
        if done:
            lines.append(done)
    return "\n".join(lines)


def soon_events(ctx: dict, now: datetime, within: timedelta = timedelta(hours=1)) -> tuple:
    """Events starting within `within`, plus a calendar problem to report (None when fine).
    A stale phone push still yields its events: an old reminder beats none."""
    events, calendar = today.events(ctx, now)
    error = calendar[len("error: "):] if calendar.startswith("error") else None
    soon = [ev for ev in events
            if ev["start"] and now < datetime.fromisoformat(ev["start"]) <= now + within]
    return soon, error
