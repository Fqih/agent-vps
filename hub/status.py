#!/usr/bin/env python3
"""Widget + dashboard server, tailnet only. Run: python3 -m hub.status"""
from __future__ import annotations

import hmac
import json
import logging
import re
import time
import urllib.parse
from contextlib import closing
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from digest import DB_PATH, REPORT_DIR, load_env
from connectors import phonecal
from hub import quota, tasks
from hub.collectors import github, jobs, queue, router9, today, vps
from hub.collectors.common import WIB

PORT = 8090
CACHE_SECONDS = 60
MAX_BODY = 64 * 1024
COLLECTORS = {"jobs": jobs.collect, "today": today.collect, "queue": queue.collect,
              "vps": vps.collect, "router": router9.collect, "quota": quota.collect,
              "github": github.collect}
TOKEN_IN_URL = re.compile(r"token=[^&\s\"]*")
LEVEL_ICON = {"ok": "🟢", "warn": "🟡", "crit": "🔴"}
log = logging.getLogger("hub.status")
_cache: dict = {}


def level(s: dict) -> str:
    v = s.get("vps", {})
    if any(name.startswith("container:") for name in v.get("down", [])) or v.get("backup_ok") is False:
        return "crit"
    warn = (v.get("disk", 0) > 85 or v.get("ram", 0) > 90 or bool(v.get("down"))
            or s.get("queue", {}).get("failed", 0) > 0
            or str(s.get("today", {}).get("calendar", "ok")).startswith("error")
            or any(isinstance(part, dict) and "error" in part for part in s.values()))
    return "warn" if warn else "ok"


def gather(ctx: dict, now: datetime, collectors: dict | None = None, clock=time.monotonic) -> dict:
    out = {"updated": now.astimezone(WIB).isoformat(timespec="seconds")}
    for name, fn in (collectors if collectors is not None else COLLECTORS).items():
        hit = _cache.get(name)
        if hit and clock() - hit[0] < CACHE_SECONDS:
            out[name] = hit[1]
            continue
        try:
            value = fn(ctx, now)
        except Exception as err:  # one broken source must not blank the widget
            log.exception("collector %s", name)
            value = {"error": f"{type(err).__name__}: {err}"[:120]}
        _cache[name] = (clock(), value)
        out[name] = value
    out["level"] = level(out)
    return out


def make_ctx(env: dict) -> dict:
    home = Path.home()
    return {"env": env, "state_db": DB_PATH, "tasks_db": tasks.DB_PATH,
            "router_db": home / "9router" / "data" / "db" / "data.sqlite", "backups": home / "backups",
            "phone_agenda": home / ".hermes" / "phone-agenda.json"}


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Hub</title><style>body{{font:15px system-ui;margin:16px;max-width:720px}}
td{{padding:2px 8px;vertical-align:top}} pre{{white-space:pre-wrap}}</style>{body}"""


def dashboard(s: dict, recent: list, token: str) -> str:
    rows = "".join(
        f"<tr><td><a href='/task/{t['id']}?token={escape(token)}'>#{t['id']}</a></td>"
        f"<td>{escape(t['title'])}</td><td>{t['status']}</td><td>{escape(t['model'] or '')}</td></tr>"
        for t in recent)
    sections = "".join(f"<h3>{name}</h3><pre>{escape(json.dumps(s[name], ensure_ascii=False, indent=1))}</pre>"
                       for name in COLLECTORS if name in s)
    return PAGE.format(body=f"<h2>{LEVEL_ICON[s['level']]} Hub · {s['updated']}</h2>"
                            f"<h3>Antrean</h3><table>{rows}</table>{sections}")


def task_page(t: dict) -> str:
    return PAGE.format(body=f"<h2>#{t['id']} {escape(t['payload'].get('title') or t['kind'])}</h2>"
                            f"<p>{t['status']} · {escape(t['model'] or '-')} · {t['finished_at'] or ''}</p>"
                            f"<pre>{escape(t['result'] or t['error'] or '')}</pre>")


class Handler(BaseHTTPRequestHandler):
    ctx: dict = {}

    def _send(self, code: int, kind: str, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self, url) -> str | None:
        """The given token when it matches STATUS_TOKEN, else None."""
        given = urllib.parse.parse_qs(url.query).get("token", [""])[0]
        expected = self.ctx["env"].get("STATUS_TOKEN", "")
        ok = expected and hmac.compare_digest(given.encode(), expected.encode())
        return given if ok else None

    def do_POST(self):
        """Phone app pushes the agenda it read from the phone's calendars."""
        url = urllib.parse.urlparse(self.path)
        if self._authorized(url) is None:
            return self._send(403, "text/plain", "forbidden")
        if url.path != "/agenda":
            return self._send(404, "text/plain", "not found")
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._send(413, "text/plain", "too large")
        try:
            phonecal.store(self.ctx["phone_agenda"], json.loads(self.rfile.read(length)), datetime.now(timezone.utc))
        except ValueError as err:  # JSONDecodeError is a ValueError too
            return self._send(400, "text/plain", f"bad agenda: {err}"[:200])
        _cache.pop("today", None)  # show the new agenda on the next /status
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        given = self._authorized(url)
        if given is None:
            return self._send(403, "text/plain", "forbidden")
        now = datetime.now(timezone.utc)
        if url.path == "/status":
            return self._send(200, "application/json; charset=utf-8",
                              json.dumps(gather(self.ctx, now), ensure_ascii=False))
        with closing(tasks.connect(self.ctx["tasks_db"])) as db:
            if url.path == "/":
                return self._send(200, "text/html; charset=utf-8",
                                  dashboard(gather(self.ctx, now), tasks.recent(db), given))
            match = re.fullmatch(r"/task/(\d+)", url.path)
            task = tasks.get(db, int(match.group(1))) if match else None
        if task:
            return self._send(200, "text/html; charset=utf-8", task_page(task))
        return self._send(404, "text/plain", "not found")

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), TOKEN_IN_URL.sub("token=***", fmt % args))


def make_server(ctx: dict, port: int = PORT) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"ctx": ctx})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> None:
    logging.basicConfig(filename=REPORT_DIR / "hub-status.log", level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s %(name)s %(message)s")
    ctx = make_ctx(load_env())
    quota.start(ctx)
    github.start(ctx)
    make_server(ctx).serve_forever()


if __name__ == "__main__":
    main()
