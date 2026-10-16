import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hub import status, tasks

NOW = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)
OK = {"vps": {"cpu": 5, "ram": 50, "disk": 20, "down": [], "backup_ok": True},
      "queue": {"running": 0, "queued": 0, "failed": 0}, "today": {"items": [], "calendar": "off"}}


class Level(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(status.level(OK), "ok")

    def test_container_down_is_crit(self):
        self.assertEqual(status.level({**OK, "vps": {**OK["vps"], "down": ["container:cv-bot"]}}), "crit")

    def test_backup_missing_is_crit(self):
        self.assertEqual(status.level({**OK, "vps": {**OK["vps"], "backup_ok": False}}), "crit")

    def test_warns(self):
        for patch in ({"vps": {**OK["vps"], "disk": 86}}, {"vps": {**OK["vps"], "ram": 91}},
                      {"vps": {**OK["vps"], "down": ["site:portfolio"]}},
                      {"queue": {**OK["queue"], "failed": 1}},
                      {"today": {"items": [], "calendar": "error: dicabut"}},
                      {"router": {"error": "OperationalError: locked"}}):
            self.assertEqual(status.level({**OK, **patch}), "warn", patch)


class Gather(unittest.TestCase):
    def setUp(self):
        status._cache.clear()

    def test_collector_error_is_isolated_and_cached(self):
        calls = []

        def broken(ctx, now):
            calls.append(1)
            raise RuntimeError("boom")
        collectors = {"vps": lambda ctx, now: OK["vps"], "router": broken}
        clock = iter([0, 0, 10, 10, 70, 70, 70, 70]).__next__
        first = status.gather({}, NOW, collectors, clock)
        status.gather({}, NOW, collectors, clock)
        status.gather({}, NOW, collectors, clock)
        self.assertEqual(first["router"], {"error": "RuntimeError: boom"})
        self.assertEqual(first["vps"], OK["vps"])
        self.assertEqual(first["updated"], "2026-10-16T09:00:00+07:00")
        self.assertEqual(first["level"], "warn")
        self.assertEqual(len(calls), 2)  # second call within 60 s used the cache


class Http(unittest.TestCase):
    def setUp(self):
        status._cache.clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tasks_db = Path(tmp.name) / "tasks.sqlite"
        db = tasks.connect(self.tasks_db)
        self.tid = tasks.enqueue(db, "llm.prompt", {"title": "Riset <b>"})
        tasks.claim(db)
        tasks.finish(db, self.tid, "hasil <script>", "m")
        db.close()

    def serve(self, token):
        ctx = {"env": {"STATUS_TOKEN": token}, "tasks_db": self.tasks_db}
        collectors = {"vps": lambda ctx, now: OK["vps"]}
        patcher = mock.patch.object(status, "COLLECTORS", collectors)
        patcher.start()
        self.addCleanup(patcher.stop)
        server = status.make_server(ctx, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)  # cleanups run LIFO: shutdown first, then close
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def test_wrong_or_missing_token_denied(self):
        base = self.serve("rahasia")
        self.assertEqual(self.get(f"{base}/status")[0], 403)
        self.assertEqual(self.get(f"{base}/status?token=salah")[0], 403)

    def test_empty_token_denies(self):
        base = self.serve("")
        self.assertEqual(self.get(f"{base}/status?token=")[0], 403)

    def test_status_json(self):
        code, body = self.get(self.serve("rahasia") + "/status?token=rahasia")
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual((data["vps"], data["level"]), (OK["vps"], "ok"))

    def test_dashboard_and_task_page_escape_html(self):
        base = self.serve("rahasia")
        code, page = self.get(f"{base}/?token=rahasia")
        self.assertEqual(code, 200)
        self.assertIn("Riset &lt;b&gt;", page)
        code, page = self.get(f"{base}/task/{self.tid}?token=rahasia")
        self.assertEqual(code, 200)
        self.assertIn("hasil &lt;script&gt;", page)
        self.assertEqual(self.get(f"{base}/task/999?token=rahasia")[0], 404)


if __name__ == "__main__":
    unittest.main()
