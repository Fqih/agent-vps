"""Quota summary from 9router usage bodies (shapes copied from the live API)."""
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hub import quota

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)


def gemini(session, weekly, reset="2026-10-16T11:52:16.000Z"):
    return {"plan": "Antigravity", "quotas": {
        "claude-sonnet-4-6": {"used": 900, "total": 1000, "remainingPercentage": 10, "resetAt": reset},
        "gemini_session": {"used": 0, "total": 1000, "remainingPercentage": session, "resetAt": reset},
        "gemini_weekly": {"used": 0, "total": 1000, "remainingPercentage": weekly, "resetAt": "2026-10-23T06:52:17.000Z"}}}


CLAUDE = {"plan": "Claude Code", "quotas": {
    "session (5h)": {"used": 33, "total": 100, "remaining": 67, "remainingPercentage": 67, "resetAt": "2026-10-16T11:30:00.377Z"},
    "weekly (7d)": {"used": 28, "total": 100, "remaining": 72, "remainingPercentage": 72, "resetAt": "2026-10-21T22:00:00.377Z"}}}
CODEX = {"plan": "plus", "quotas": {
    "session": {"used": 3, "total": 100, "remaining": 97, "resetAt": "2026-10-16T11:23:28.000Z"},
    "weekly": {"used": 12, "total": 100, "remaining": 88, "resetAt": "2026-10-22T06:13:18.000Z"}}}


class Summarize(unittest.TestCase):
    def test_average_per_provider_and_soonest_reset(self):
        out = quota.summarize({"antigravity": [gemini(100, 90), gemini(50, 70, "2026-10-16T09:00:00.000Z")],
                               "claude": [CLAUDE], "codex": [CODEX]})
        self.assertEqual(out["gemini"], {"accounts": 2, "session": 75, "weekly": 80, "reset": "16:00"})
        self.assertEqual(out["claude"], {"accounts": 1, "session": 67, "weekly": 72, "reset": "18:30"})
        self.assertEqual(out["codex"], {"accounts": 1, "session": 97, "weekly": 88, "reset": "18:23"})

    def test_gemini_ignores_non_gemini_models(self):
        self.assertEqual(quota.summarize({"antigravity": [gemini(100, 100)]})["gemini"]["session"], 100)

    def test_missing_provider_is_absent(self):
        self.assertEqual(quota.summarize({"codex": [CODEX]}), {"codex": {"accounts": 1, "session": 97, "weekly": 88,
                                                                          "reset": "18:23"}})

    def test_unlimited_counts_as_full(self):
        body = {"quotas": {"session": {"unlimited": True}, "weekly": {"used": 50, "total": 100}}}
        self.assertEqual(quota.summarize({"codex": [body]})["codex"]["session"], 100)
        self.assertEqual(quota.summarize({"codex": [body]})["codex"]["weekly"], 50)


class Malformed(unittest.TestCase):
    def test_bad_account_does_not_hide_good_one(self):
        bad = [{"quotas": None}, "oops", {"quotas": {"session": "x", "weekly": {"remainingPercentage": "lots"}}},
               {"quotas": {"session": {"used": 1, "total": 100, "resetAt": "not a date"}}}]
        out = quota.summarize({"codex": bad + [CODEX]})["codex"]
        self.assertEqual((out["accounts"], out["weekly"], out["reset"]), (5, 88, "18:23"))
        self.assertEqual(out["session"], 98)  # 99 from the bad-reset account, 97 from CODEX

    def test_failed_account_counts_as_missing(self):
        out = quota.summarize({"codex": [CODEX, None]})["codex"]
        self.assertEqual((out["accounts"], out["missing"], out["session"]), (2, 1, 97))

    def test_reset_without_timezone_is_ignored(self):
        naive = {"quotas": {"session": {"remaining": 50, "total": 100, "resetAt": "2026-10-16T01:00:00"}}}
        self.assertEqual(quota.summarize({"codex": [naive, CODEX]})["codex"]["reset"], "18:23")


class FakeRouter(BaseHTTPRequestHandler):
    usage_status = 200
    logins = 0
    fail_ids: set = set()

    def do_POST(self):
        type(self).logins += 1
        self.send_response(200)
        self.send_header("Set-Cookie", "auth_token=t; Path=/")
        self.end_headers()

    def do_GET(self):
        ok = ("auth_token=t" in (self.headers.get("Cookie") or "") and self.usage_status == 200
              and self.path.rsplit("/", 1)[-1] not in self.fail_ids)
        body = json.dumps(CODEX).encode()
        self.send_response(200 if ok else 500)
        self.end_headers()
        self.wfile.write(body if ok else b"{}")

    def log_message(self, *args):
        pass


class Fetch(unittest.TestCase):
    def setUp(self):
        FakeRouter.usage_status, FakeRouter.logins, FakeRouter.fail_ids = 200, 0, set()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRouter)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.db = Path(tempfile.mkdtemp()) / "data.sqlite"
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE providerConnections (id TEXT, provider TEXT, isActive INTEGER, data TEXT)")
        self.ctx = {"router_db": self.db, "env": {"ROUTER_DASHBOARD_PASSWORD": "pw",
                    "ROUTER_DASHBOARD_URL": f"http://127.0.0.1:{self.server.server_port}"}}

    def add(self, conn_id, provider, active=1):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO providerConnections VALUES (?, ?, ?, '{}')", (conn_id, provider, active))

    def test_fetches_eligible_accounts(self):
        self.add("a", "codex")
        self.add("b", "codex", active=0)
        self.add("g", "github")
        self.assertEqual(quota.fetch(self.ctx), {"codex": [CODEX]})

    def test_failed_account_is_kept_as_none(self):
        self.add("a", "codex")
        self.add("b", "codex")
        FakeRouter.fail_ids = {"b"}
        self.assertEqual(quota.fetch(self.ctx), {"codex": [CODEX, None]})

    def test_no_eligible_accounts_is_empty_without_login(self):
        self.add("g", "github")
        self.assertEqual(quota.fetch(self.ctx), {})
        self.assertEqual(FakeRouter.logins, 0)

    def test_all_usage_requests_failing_raises(self):
        self.add("a", "codex")
        FakeRouter.usage_status = 500
        with self.assertRaises(OSError):
            quota.fetch(self.ctx)


class Collect(unittest.TestCase):
    def test_loading_before_first_refresh(self):
        quota._state.update(value=None, error=None)
        self.assertEqual(quota.collect({}, NOW), {"loading": True})

    def test_empty_success_is_not_loading(self):
        quota._state.update(value=None, error=None)
        quota.refresh_once({}, fetch=lambda ctx: {})
        self.assertEqual(quota.collect({}, NOW), {})

    def test_returns_last_background_value(self):
        quota._state["value"] = {"codex": {"accounts": 1}}
        self.assertEqual(quota.collect({}, NOW), {"codex": {"accounts": 1}})

    def test_failed_refresh_keeps_last_good_value(self):
        quota._state["value"] = {"codex": {"accounts": 1}}
        quota.refresh_once({}, fetch=lambda ctx: (_ for _ in ()).throw(OSError("router down")))
        self.assertEqual(quota._state["value"], {"codex": {"accounts": 1}})


if __name__ == "__main__":
    unittest.main()
