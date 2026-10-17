"""Today's agenda: calendar events plus tracker follow-ups that are due."""
from __future__ import annotations

import urllib.error
from contextlib import closing
from datetime import datetime

from connectors import gcal, phonecal
from connectors.google_auth import AuthError, TokenMissing
from hub.collectors.common import WIB, ro


def events(ctx: dict, now: datetime) -> tuple:
    """Today's calendar events and the calendar label: Google when logged in, else the phone's push."""
    day = now.astimezone(WIB).date()
    try:
        kwargs = {"token_fn": ctx["token_fn"]} if ctx.get("token_fn") else {}
        return gcal.list_events(day, **kwargs), "ok"
    except TokenMissing:
        phone = ctx.get("phone_agenda")
        label = phonecal.state(phone, now) if phone else None
        return (phonecal.list_events(phone, day), label) if label else ([], "off")
    except (AuthError, urllib.error.URLError, OSError, ValueError) as err:
        return [], f"error: {err}"[:80]


def collect(ctx: dict, now: datetime) -> dict:
    found, calendar = events(ctx, now)
    items = [{"time": ev["time"], "title": ev["title"], "kind": "event"} for ev in found]
    with closing(ro(ctx["state_db"])) as db:
        rows = db.execute("SELECT title, company FROM jobs WHERE status IN ('dilamar', 'interview') "
                          "AND next_remind <= ? ORDER BY next_remind", (now.isoformat(),)).fetchall()
    items.extend({"time": None, "title": f"Follow-up {company or title}", "kind": "followup"}
                 for title, company in rows)
    return {"items": items, "calendar": calendar}
