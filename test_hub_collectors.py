import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import monitor
import tracker
from connectors.google_auth import AuthError, TokenMissing
from hub import tasks
from hub.collectors import jobs, queue, router9, today, vps

NOW = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)  # 09:00 WIB


class Collectors(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.ctx = {"state_db": root / "state.sqlite", "tasks_db": root / "tasks.sqlite",
                    "router_db": root / "router.sqlite", "backups": root / "backups",
                    "meminfo": root / "meminfo", "loadavg": root / "loadavg"}
        with sqlite3.connect(self.ctx["state_db"]) as db:
            tracker.init(db)
            monitor.init(db)
            rows = [  # url, title, company, status, created_at, next_remind
                ("u1", "Data Analyst", "PT A", "baru", NOW - timedelta(hours=2), None),
                ("u2", "BI", "PT B", "baru", NOW - timedelta(days=3), None),
                ("u3", "ML", "PT C", "dilamar", NOW - timedelta(days=9), NOW - timedelta(hours=1)),
                ("u4", "DS", "PT D", "interview", NOW - timedelta(days=9), NOW + timedelta(days=2)),
                ("u5", "DE", "PT E", "disimpan", NOW, None)]
            for url, title, company, status, created, remind in rows:
                db.execute("INSERT INTO jobs (url, title, company, status, created_at, next_remind) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (url, title, company, status, created.isoformat(),
                                                          remind.isoformat() if remind else None))
            db.execute("INSERT INTO checks VALUES ('container:cv-bot', 0, 3, ?, 'tidak jalan')", (NOW.isoformat(),))
            db.execute("INSERT INTO checks VALUES ('disk', 1, 0, ?, '22%')", (NOW.isoformat(),))

    def tearDown(self):
        self.dir.cleanup()

    def test_jobs_counts(self):
        self.assertEqual(jobs.collect(self.ctx, NOW), {
            "new_matches": 1, "drafts": 0, "active": 3, "interview": 1, "followup_due": 1})

    def test_today_merges_events_and_followups(self):
        self.ctx["token_fn"] = lambda: "tok"
        events = [{"id": "e1", "title": "Interview PT D", "start": "2026-10-16T10:00:00+07:00", "time": "10:00"}]
        with mock.patch("connectors.gcal.list_events", return_value=events):
            out = today.collect(self.ctx, NOW)
        self.assertEqual(out, {"calendar": "ok", "items": [
            {"time": "10:00", "title": "Interview PT D", "kind": "event"},
            {"time": None, "title": "Follow-up PT C", "kind": "followup"}]})

    def test_no_token_is_off_not_error(self):
        with mock.patch("connectors.gcal.list_events", side_effect=TokenMissing("x")):
            self.assertEqual(today.collect(self.ctx, NOW)["calendar"], "off")

    def test_revoked_token_is_error(self):
        with mock.patch("connectors.gcal.list_events", side_effect=AuthError("dicabut")):
            self.assertTrue(today.collect(self.ctx, NOW)["calendar"].startswith("error"))

    def test_queue_counts(self):
        db = tasks.connect(self.ctx["tasks_db"])
        tasks.enqueue(db, "k", {}, now=NOW)
        db.close()
        self.assertEqual(queue.collect(self.ctx, NOW), {"running": 0, "queued": 1, "failed": 0})

    def test_vps(self):
        self.ctx["meminfo"].write_text("MemTotal:  2000000 kB\nMemAvailable:  800000 kB\n")
        self.ctx["loadavg"].write_text("0.50 0.40 0.30 1/200 999\n")
        day = self.ctx["backups"] / "2026-10-16"
        day.mkdir(parents=True)
        (day / "9router.sqlite.gz").write_bytes(b"x")
        out = vps.collect(self.ctx, NOW)
        self.assertEqual((out["ram"], out["down"], out["backup_ok"]), (60, ["container:cv-bot"], True))
        self.assertTrue(0 <= out["cpu"] <= 100 and 0 <= out["disk"] <= 100)

    def test_vps_backup_stale(self):
        self.ctx["meminfo"].write_text("MemTotal:  2000000 kB\nMemAvailable:  800000 kB\n")
        self.ctx["loadavg"].write_text("0.10 0 0 1/1 1\n")
        old = self.ctx["backups"] / "2026-10-13"
        old.mkdir(parents=True)
        (old / "9router.sqlite.gz").write_bytes(b"x")
        self.assertFalse(vps.collect(self.ctx, NOW)["backup_ok"])

    def test_router_active_over_total(self):
        with sqlite3.connect(self.ctx["router_db"]) as db:
            db.execute("CREATE TABLE providerConnections (id TEXT, provider TEXT, isActive INTEGER, data TEXT)")
            rows = [("1", "antigravity", 1, {"testStatus": "active"}), ("2", "antigravity", 1, {"testStatus": "unavailable"}),
                    ("3", "antigravity", 0, {"testStatus": "active"}), ("4", "codex", 1, {"testStatus": "active"})]
            db.executemany("INSERT INTO providerConnections VALUES (?, ?, ?, ?)",
                           [(i, p, a, json.dumps(d)) for i, p, a, d in rows])
        self.assertEqual(router9.collect(self.ctx, NOW), {"ag": "1/2", "cx": "1/1"})


if __name__ == "__main__":
    unittest.main()
