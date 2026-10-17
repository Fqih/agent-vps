"""GitHub contribution calendar, parsed from the public profile HTML (no token needed)."""
from __future__ import annotations

import logging
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone

from hub.collectors import common
from hub.collectors.common import WIB

REFRESH_SECONDS = 3600
DAY = re.compile(r'<td[^>]*data-date="(\d{4}-\d\d-\d\d)"[^>]*>')
ATTR = re.compile(r'(id|data-level)="([^"]*)"')
TIP = re.compile(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>\s*(No|\d+) contributions? on')
log = logging.getLogger("hub.github")
_state: dict = {"value": None, "error": None}


def fetch(user: str) -> str:
    req = urllib.request.Request(f"https://github.com/users/{user}/contributions",
                                 headers={"User-Agent": "hub-status"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8", "replace")


def parse(html: str, today: date) -> dict:
    counts = {cell: 0 if n == "No" else int(n) for cell, n in TIP.findall(html)}
    days = {}
    for m in DAY.finditer(html):
        attrs = dict(ATTR.findall(m.group(0)))
        days[date.fromisoformat(m.group(1))] = (int(attrs.get("data-level", 0)), counts.get(attrs.get("id"), 0))
    if not days:
        raise ValueError("no contribution calendar in page")
    first = min(days) - timedelta(days=(min(days).weekday() + 1) % 7)  # back to Sunday
    weeks = [[days.get(first + timedelta(w * 7 + d), (-1, 0))[0] for d in range(7)]
             for w in range((max(days) - first).days // 7 + 1)]
    streak, d = 0, today if days.get(today, (0, 0))[1] else today - timedelta(days=1)
    while days.get(d, (0, 0))[1]:
        streak, d = streak + 1, d - timedelta(days=1)
    return {"total": sum(c for _, c in days.values()), "today": days.get(today, (0, 0))[1],
            "streak": streak, "weeks": weeks}


def refresh_once(ctx: dict, now: datetime, fetch=fetch) -> None:
    user = ctx["env"].get("GITHUB_USER", "Fqih")
    try:
        _state["value"] = dict(parse(fetch(user), now.astimezone(WIB).date()), user=user)
        _state["error"] = None
    except Exception as err:  # keep the last calendar; GitHub hiccups are not worth a warning
        log.warning("github contributions: %s", err)
        _state["error"] = f"{type(err).__name__}: {err}"[:120]


def start(ctx: dict):
    return common.every("github", REFRESH_SECONDS, lambda: refresh_once(ctx, datetime.now(timezone.utc)))


def collect(ctx: dict, now: datetime) -> dict:
    if _state["value"] is not None:
        return _state["value"]
    return {"error": _state["error"]} if _state["error"] else {"loading": True}
