"""Google Calendar (primary calendar) over REST."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone

from connectors.google_auth import access_token

API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
WIB = timezone(timedelta(hours=7))


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _event(item: dict) -> dict:
    raw = item.get("start", {}).get("dateTime")
    start = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(WIB) if raw else None
    return {"id": item.get("id"), "title": item.get("summary") or "(tanpa judul)",
            "start": start.isoformat() if start else None, "time": start.strftime("%H:%M") if start else None}


def list_events(day: date, token_fn=access_token) -> list:
    start = datetime.combine(day, dtime.min, WIB)
    query = urllib.parse.urlencode({"timeMin": start.isoformat(), "timeMax": (start + timedelta(days=1)).isoformat(),
                                    "singleEvents": "true", "orderBy": "startTime", "maxResults": "20"})
    data = _request("GET", f"{API}?{query}", token_fn())
    return [_event(item) for item in data.get("items", [])]


def create_event(summary: str, start: datetime, end: datetime, description: str = "",
                 token_fn=access_token) -> str:
    body = {"summary": summary, "description": description,
            "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
    return _request("POST", API, token_fn(), body)["id"]
