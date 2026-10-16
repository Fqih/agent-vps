"""Morning push text and the 'interview in 1 hour' check, used by infobot's scheduler."""
from __future__ import annotations

import urllib.error
from datetime import datetime, timedelta

from connectors import gcal
from connectors.google_auth import AuthError, TokenMissing
from hub.collectors import jobs, today
from hub.collectors.common import WIB


def morning_text(ctx: dict, now: datetime) -> str:
    agenda = today.collect(ctx, now)["items"]
    counts = jobs.collect(ctx, now)
    lines = [f"{item['time']} {item['title']}" if item["time"] else item["title"] for item in agenda]
    lines = lines or ["Tidak ada agenda hari ini."]
    lines.append(f"{counts['new_matches']} lowongan baru · {counts['active']} aktif · "
                 f"{counts['followup_due']} follow-up jatuh tempo")
    return "\n".join(lines)


def soon_events(ctx: dict, now: datetime, within: timedelta = timedelta(hours=1)) -> tuple:
    try:
        kwargs = {"token_fn": ctx["token_fn"]} if ctx.get("token_fn") else {}
        events = gcal.list_events(now.astimezone(WIB).date(), **kwargs)
    except TokenMissing:
        return [], None
    except (AuthError, urllib.error.URLError, OSError, ValueError) as err:
        return [], str(err)
    soon = [ev for ev in events
            if ev["start"] and now < datetime.fromisoformat(ev["start"]) <= now + within]
    return soon, None
