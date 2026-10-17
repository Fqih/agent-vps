"""Agenda pushed by the Hub phone app, read from the calendars synced on the phone.

The app POSTs today's and tomorrow's events to /agenda on every refresh; the
latest push replaces the previous one. Used when Google OAuth is not set up.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from hub.collectors.common import WIB

MAX_EVENTS = 100
MAX_TITLE = 200
STALE = timedelta(hours=24)


def _event(raw) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("title"), str) or not isinstance(raw.get("id"), str):
        raise ValueError("event needs string id and title")
    day = date.fromisoformat(raw.get("date") or "")  # ValueError on anything else
    start = raw.get("start")
    if start is not None:
        when = datetime.fromisoformat(start)
        if when.tzinfo is None:
            raise ValueError("start needs a UTC offset")
        start = when.astimezone(WIB).isoformat()
    return {"id": raw["id"][:100], "title": raw["title"][:MAX_TITLE] or "(tanpa judul)",
            "start": None if raw.get("all_day") is True else start, "date": day.isoformat()}


def store(path: Path, payload, now: datetime) -> None:
    """Validate and atomically replace the stored agenda; raises ValueError and keeps the old one."""
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError(f"events must be a list of at most {MAX_EVENTS}")
    data = {"received": now.astimezone(WIB).isoformat(timespec="seconds"), "events": [_event(e) for e in events]}
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w") as f:  # mkstemp creates the file with mode 600
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _load(path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def list_events(path: Path, day: date) -> list:
    """Same shape as connectors.gcal.list_events: all-day events first, then by start."""
    data = _load(path) or {"events": []}
    events = [e for e in data["events"] if e["date"] == day.isoformat()]
    events.sort(key=lambda e: (e["start"] is not None, e["start"] or ""))
    return [{"id": e["id"], "title": e["title"], "start": e["start"],
             "time": e["start"][11:16] if e["start"] else None} for e in events]


def state(path: Path, now: datetime) -> str | None:
    """Calendar label for /status: None when the phone never pushed, error when the push is stale."""
    data = _load(path)
    if not data:
        return None
    received = datetime.fromisoformat(data["received"])
    if now - received > STALE:
        return f"error: data kalender HP basi ({int((now - received).total_seconds() // 3600)} jam)"
    return f"hp · {received.strftime('%H:%M')}"
