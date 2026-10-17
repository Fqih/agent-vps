"""Minimal Telegram Bot API client (stdlib only)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MAX_IMAGE = 10 * 1024 * 1024


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


def _download(env: dict, file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{env['TELEGRAM_BOT_TOKEN']}/{file_path}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read(MAX_IMAGE + 1)


def save_image(env: dict, message: dict, dest: Path, call=call, download=None) -> Path | None:
    """Save the largest photo (or an image sent as a file) to dest with mode 600; None if not an image."""
    doc = message.get("document") or {}
    if message.get("photo"):
        file_id = message["photo"][-1]["file_id"]
    elif str(doc.get("mime_type", "")).startswith("image/"):
        file_id = doc["file_id"]
    else:
        return None
    info = call(env, "getFile", file_id=file_id).get("result") or {}
    if not info.get("file_path") or (info.get("file_size") or 0) > MAX_IMAGE:
        raise ValueError("image missing or larger than 10 MB")
    data = (download or (lambda path: _download(env, path)))(info["file_path"])
    if len(data) > MAX_IMAGE:
        raise ValueError("image larger than 10 MB")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    suffix = Path(info["file_path"]).suffix or ".jpg"
    path = dest / f"{time.strftime('%Y%m%d-%H%M%S')}-{message.get('message_id', 0)}{suffix}"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path
