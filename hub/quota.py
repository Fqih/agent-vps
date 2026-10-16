"""Remaining 9router quota per provider (average over active accounts).

Fetching usage for every account takes seconds, so a background thread
refreshes it every 15 minutes and the collector only returns the last result.
"""
from __future__ import annotations

import http.cookiejar
import json
import logging
import threading
import urllib.request
from contextlib import closing
from datetime import datetime

from hub.collectors.common import WIB, ro

REFRESH_SECONDS = 15 * 60
BASE_URL = "http://127.0.0.1:20128"
# provider in 9router -> (name in /status, session quota key, weekly quota key)
PROVIDERS = {"antigravity": ("gemini", "gemini_session", "gemini_weekly"),
             "claude": ("claude", "session (5h)", "weekly (7d)"),
             "codex": ("codex", "session", "weekly")}
log = logging.getLogger("hub.quota")
_state: dict = {"value": None, "error": None}


def _remaining(q: dict) -> float | None:
    if q.get("unlimited"):
        return 100.0
    if q.get("remainingPercentage") is not None:
        return float(q["remainingPercentage"])
    total = q.get("total")
    if not total:
        return None
    left = q["remaining"] if q.get("remaining") is not None else total - q.get("used", 0)
    return left * 100 / total


def _avg(values: list) -> int | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else None


def _reset(quotas: list) -> str | None:
    times = [datetime.fromisoformat(q["resetAt"].replace("Z", "+00:00")) for q in quotas if q.get("resetAt")]
    return min(times).astimezone(WIB).strftime("%H:%M") if times else None


def summarize(usages: dict) -> dict:
    """usages: 9router provider -> list of /api/usage bodies, one per account."""
    out = {}
    for provider, (name, session_key, weekly_key) in PROVIDERS.items():
        bodies = usages.get(provider)
        if not bodies:
            continue
        sessions = [b.get("quotas", {}).get(session_key, {}) for b in bodies]
        weeklies = [b.get("quotas", {}).get(weekly_key, {}) for b in bodies]
        out[name] = {"accounts": len(bodies), "session": _avg([_remaining(q) for q in sessions]),
                     "weekly": _avg([_remaining(q) for q in weeklies]), "reset": _reset(sessions)}
    return out


def fetch(ctx: dict) -> dict:
    env = ctx["env"]
    with closing(ro(ctx["router_db"])) as db:
        rows = db.execute("SELECT id, provider FROM providerConnections WHERE isActive = 1").fetchall()
    base = env.get("ROUTER_DASHBOARD_URL", BASE_URL).rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login = json.dumps({"password": env["ROUTER_DASHBOARD_PASSWORD"]}).encode()
    opener.open(urllib.request.Request(base + "/api/auth/login", login,
                                       {"Content-Type": "application/json"}), timeout=15).close()
    usages: dict = {}
    for conn_id, provider in rows:
        if provider not in PROVIDERS:
            continue
        try:
            with opener.open(f"{base}/api/usage/{conn_id}", timeout=30) as resp:
                usages.setdefault(provider, []).append(json.load(resp))
        except Exception as err:  # one bad account must not hide the rest
            log.warning("usage %s %s: %s", provider, conn_id, err)
    return usages


def refresh_once(ctx: dict, fetch=fetch) -> None:
    try:
        _state["value"], _state["error"] = summarize(fetch(ctx)), None
    except Exception as err:
        log.exception("quota refresh")
        _state["error"] = f"{type(err).__name__}: {err}"[:120]


def start(ctx: dict, every: int = REFRESH_SECONDS) -> threading.Thread:
    def loop():
        while True:
            refresh_once(ctx)
            threading.Event().wait(every)
    thread = threading.Thread(target=loop, name="quota", daemon=True)
    thread.start()
    return thread


def collect(ctx: dict, now: datetime) -> dict:
    if _state["value"] is not None:
        return _state["value"]
    return {"error": _state["error"]} if _state["error"] else {}
