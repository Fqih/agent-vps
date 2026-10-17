"""Remaining 9router quota per provider (average over active accounts).

Fetching usage for every account takes seconds, so a background thread
refreshes it every 15 minutes and the collector only returns the last result.
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
import math
import urllib.request
from contextlib import closing
from datetime import datetime, timezone

from hub.collectors import common
from hub.collectors.common import WIB, ro

REFRESH_SECONDS = 15 * 60
BASE_URL = "http://127.0.0.1:20128"
# provider in 9router -> (name in /status, session quota key, weekly quota key)
PROVIDERS = {"antigravity": ("gemini", "gemini_session", "gemini_weekly"),
             "claude": ("claude", "session (5h)", "weekly (7d)"),
             "codex": ("codex", "session", "weekly")}
log = logging.getLogger("hub.quota")
_state: dict = {"value": None, "error": None}


def _num(value) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return float(value) if ok else None


def _remaining(q: dict) -> float | None:
    if q.get("unlimited") is True:
        return 100.0
    pct = _num(q.get("remainingPercentage"))
    if pct is not None:
        return pct
    total, left, used = _num(q.get("total")), _num(q.get("remaining")), _num(q.get("used"))
    if not total:
        return None
    if left is None:
        left = total - used if used is not None else None
    return None if left is None else left * 100 / total


def _avg(values: list) -> int | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else None


def _when(value) -> datetime | None:
    """Reset time as aware UTC; anything unparsable or without an offset is unknown."""
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return when.astimezone(timezone.utc) if when.tzinfo else None


def _reset(quotas: list) -> str | None:
    times = [t for t in (_when(q.get("resetAt")) for q in quotas) if t]
    return min(times).astimezone(WIB).strftime("%H:%M") if times else None


def _quota(body, key: str) -> dict:
    quotas = body.get("quotas") if isinstance(body, dict) else None
    q = quotas.get(key) if isinstance(quotas, dict) else None
    return q if isinstance(q, dict) else {}


def summarize(usages: dict) -> dict:
    """usages: 9router provider -> list of /api/usage bodies, one per account (None = fetch failed)."""
    out = {}
    for provider, (name, session_key, weekly_key) in PROVIDERS.items():
        bodies = usages.get(provider)
        if not bodies:
            continue
        sessions = [_quota(b, session_key) for b in bodies]
        weeklies = [_quota(b, weekly_key) for b in bodies]
        out[name] = {"accounts": len(bodies), "session": _avg([_remaining(q) for q in sessions]),
                     "weekly": _avg([_remaining(q) for q in weeklies]), "reset": _reset(sessions)}
        missing = bodies.count(None)  # accounts whose usage request failed; averages cover the rest
        if missing:
            out[name]["missing"] = missing
    return out


def fetch(ctx: dict) -> dict:
    env = ctx["env"]
    with closing(ro(ctx["router_db"])) as db:
        rows = [(conn_id, provider) for conn_id, provider in
                db.execute("SELECT id, provider FROM providerConnections WHERE isActive = 1") if provider in PROVIDERS]
    if not rows:
        return {}
    base = env.get("ROUTER_DASHBOARD_URL", BASE_URL).rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login = json.dumps({"password": env["ROUTER_DASHBOARD_PASSWORD"]}).encode()
    opener.open(urllib.request.Request(base + "/api/auth/login", login,
                                       {"Content-Type": "application/json"}), timeout=15).close()
    usages: dict = {}
    for conn_id, provider in rows:
        try:
            with opener.open(f"{base}/api/usage/{conn_id}", timeout=30) as resp:
                usages.setdefault(provider, []).append(json.load(resp))
        except Exception as err:  # one bad account must not hide the rest
            log.warning("usage %s %s: %s", provider, conn_id, err)
            usages.setdefault(provider, []).append(None)
    if not any(b is not None for bodies in usages.values() for b in bodies):  # dashboard up but every account failed: keep the last good numbers
        raise OSError(f"usage failed for all {len(rows)} accounts")
    return usages


def refresh_once(ctx: dict, fetch=fetch) -> None:
    try:
        _state["value"], _state["error"] = summarize(fetch(ctx)), None
    except Exception as err:
        log.exception("quota refresh")
        _state["error"] = f"{type(err).__name__}: {err}"[:120]


def start(ctx: dict, every: int = REFRESH_SECONDS):
    return common.every("quota", every, lambda: refresh_once(ctx))


def collect(ctx: dict, now: datetime) -> dict:
    if _state["value"] is not None:
        return _state["value"]
    return {"error": _state["error"]} if _state["error"] else {"loading": True}
