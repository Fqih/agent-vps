"""GitHub contribution calendar, parsed from the public profile HTML (no token needed)."""
from __future__ import annotations

import logging
import re
import time
import urllib.request
from datetime import date, datetime, timedelta

from hub.collectors.common import WIB

TTL_SECONDS = 3600
RETRY_SECONDS = 600
DAY = re.compile(r'<td[^>]*data-date="(\d{4}-\d\d-\d\d)"[^>]*>')
ATTR = re.compile(r'(id|data-level)="([^"]*)"')
TIP = re.compile(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>\s*(No|\d+) contributions? on')
log = logging.getLogger("hub.github")
_cache: dict = {}


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


def collect(ctx: dict, now: datetime) -> dict:
    """Hourly; a failed fetch keeps the last good calendar and retries after 10 minutes."""
    if _cache.get("value") is not None and time.monotonic() - _cache.get("at", 0) < TTL_SECONDS:
        return _cache["value"]
    if _cache.get("value") is None and time.monotonic() - _cache.get("failed", -RETRY_SECONDS) < RETRY_SECONDS:
        raise RuntimeError(_cache.get("error", "github unavailable"))
    user = ctx["env"].get("GITHUB_USER", "Fqih")
    try:
        value = dict(parse(ctx.get("github_fetch", fetch)(user), now.astimezone(WIB).date()), user=user)
    except Exception as err:
        log.warning("github contributions: %s", err)
        _cache.update(failed=time.monotonic(), error=f"{type(err).__name__}: {err}"[:120])
        if _cache.get("value") is None:
            raise
        _cache["at"] = time.monotonic() - TTL_SECONDS + RETRY_SECONDS
        return _cache["value"]
    _cache.update(value=value, at=time.monotonic())
    return value
