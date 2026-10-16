"""Chat over 9router with an ordered model chain and a short memory of dead models."""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODELS_PATH = Path(__file__).with_name("models.json")
DEAD_FOR = timedelta(hours=6)
TIMEOUT = 180
log = logging.getLogger("hub.llm")
_dead: dict = {}


class ChainFailed(RuntimeError):
    """Every model in the chain failed or is marked dead."""


def load_chains(path=MODELS_PATH) -> dict:
    return json.loads(Path(path).read_text())


def _not_found(code: int, body: str) -> bool:
    # 9router answers 503 and puts the upstream status in the message: "[provider/model] [404]: ..."
    return code == 404 or "] [404]:" in body


def _call(model: str, messages: list, cfg: dict) -> str:
    url = cfg.get("base_url", "http://127.0.0.1:20128/v1").rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url, data=json.dumps({"model": model, "stream": False, "messages": messages}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg.get('api_key', '')}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    text = (data["choices"][0]["message"]["content"] or "").strip()
    if not text:
        raise ValueError("empty answer")
    return text


def chat(chain: str, messages: list, cfg: dict, chains: dict | None = None,
         now: datetime | None = None) -> tuple:
    now = now or datetime.now(timezone.utc)
    errors = []
    for model in (chains or load_chains())[chain]:
        if _dead.get(model, now) > now:
            continue
        try:
            return _call(model, messages, cfg), model
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            if _not_found(err.code, body):
                _dead[model] = now + DEAD_FOR
            errors.append(f"{model}: HTTP {err.code}")
        except (urllib.error.URLError, socket.timeout, OSError, KeyError, IndexError, ValueError) as err:
            errors.append(f"{model}: {err}")
        log.warning("model gagal: %s", errors[-1])
    raise ChainFailed("; ".join(errors) or f"semua model di chain {chain} sedang ditandai mati")
