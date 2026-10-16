"""Push notifications through the self-hosted ntfy server (Telegram fallback for high priority)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from html import escape

import tg

log = logging.getLogger("hub.notify")
PRIORITY = {"high": 5, "default": 3, "low": 2}


def publish(env: dict, topic: str, title: str, message: str, priority: str = "default",
            click: str | None = None, tags: list | None = None, fallback: bool = True) -> bool:
    """Send one push. Never raises; True when ntfy accepted it."""
    body = {"topic": topic, "title": title, "message": message, "priority": PRIORITY.get(priority, 3)}
    if click:
        body["click"] = click
    if tags:
        body["tags"] = tags
    url = env.get("NTFY_URL", "").rstrip("/")
    try:
        if not url:
            raise ValueError("NTFY_URL not set")
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {env.get('NTFY_TOKEN', '')}"})
        with urllib.request.urlopen(req, timeout=15):
            return True
    except (urllib.error.URLError, OSError, ValueError) as err:
        log.warning("ntfy %s gagal: %s", topic, err)
    if priority == "high" and fallback:
        try:
            tg.send(env, f"<b>{escape(title)}</b>\n{escape(message)}")
        except Exception:  # the fallback must not take the caller down either
            log.exception("telegram fallback gagal")
    return False
