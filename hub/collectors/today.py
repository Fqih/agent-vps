"""Today's agenda: calendar events plus tracker follow-ups that are due."""
from __future__ import annotations

import urllib.error
from contextlib import closing
from datetime import datetime

from connectors import gcal
from connectors.google_auth import AuthError, TokenMissing
from hub.collectors.common import WIB, ro


def collect(ctx: dict, now: datetime) -> dict:
    items, calendar = [], "ok"
    try:
        kwargs = {"token_fn": ctx["token_fn"]} if ctx.get("token_fn") else {}
        for ev in gcal.list_events(now.astimezone(WIB).date(), **kwargs):
            items.append({"time": ev["time"], "title": ev["title"], "kind": "event"})
    except TokenMissing:
        calendar = "off"
    except (AuthError, urllib.error.URLError, OSError, ValueError) as err:
        calendar = f"error: {err}"[:80]
    with closing(ro(ctx["state_db"])) as db:
        rows = db.execute("SELECT title, company FROM jobs WHERE status IN ('dilamar', 'interview') "
                          "AND next_remind <= ? ORDER BY next_remind", (now.isoformat(),)).fetchall()
    items.extend({"time": None, "title": f"Follow-up {company or title}", "kind": "followup"}
                 for title, company in rows)
    return {"items": items, "calendar": calendar}
