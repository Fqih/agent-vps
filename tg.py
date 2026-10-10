"""Minimal Telegram Bot API client (stdlib only)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def call(env: dict, method: str, http_timeout: int = 30, **payload) -> dict:
    url = f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/{method}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read()
        return json.loads(body) if body else {"ok": False, "description": str(err)}


def send(env: dict, text: str, buttons: list | None = None) -> dict:
    payload = {"chat_id": env["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return call(env, "sendMessage", **payload)


def button(label: str, data: str) -> dict:
    return {"text": label, "callback_data": data}
