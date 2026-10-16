import os
import stat
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from hub import tasks

T0 = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)


def db():
    return tasks.connect(":memory:")


class Queue(unittest.TestCase):
    def test_memory_db_creates_no_file(self):
        cwd = os.getcwd()
        os.chdir(tempfile.mkdtemp())
        try:
            tasks.connect(":memory:").close()
            self.assertEqual(os.listdir("."), [])
        finally:
            os.chdir(cwd)

    def test_db_files_private_to_owner(self):
        path = Path(tempfile.mkdtemp()) / "tasks.sqlite"
        old = os.umask(0o022)
        try:
            db = tasks.connect(path)
            tasks.enqueue(db, "k", {"prompt": "rahasia"})
            db.close()
        finally:
            os.umask(old)
        for f in path.parent.glob("tasks.sqlite*"):
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600, f.name)

    def test_enqueue_roundtrip_unicode(self):
        conn = db()
        tid = tasks.enqueue(conn, "llm.prompt", {"prompt": "Lamar PT Ölçü 🎯"}, now=T0)
        task = tasks.get(conn, tid)
        self.assertEqual(task["payload"], {"prompt": "Lamar PT Ölçü 🎯"})
        self.assertEqual((task["status"], task["chain"], task["attempts"]), ("queued", "fast", 0))

    def test_dedup_returns_existing_id(self):
        conn = db()
        a = tasks.enqueue(conn, "llm.prompt", {"prompt": "a"}, dedup_key="cv:7", now=T0)
        b = tasks.enqueue(conn, "llm.prompt", {"prompt": "b"}, dedup_key="cv:7", now=T0)
        self.assertEqual(a, b)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)

    def test_claim_oldest_first_and_marks_running(self):
        conn = db()
        first = tasks.enqueue(conn, "k", {}, now=T0)
        tasks.enqueue(conn, "k", {}, now=T0 + timedelta(seconds=1))
        task = tasks.claim(conn, now=T0 + timedelta(seconds=2))
        self.assertEqual((task["id"], task["status"]), (first, "running"))

    def test_claim_respects_run_after(self):
        conn = db()
        tid = tasks.enqueue(conn, "k", {}, now=T0)
        tasks.claim(conn, now=T0)
        tasks.retry_or_fail(conn, tid, "boom", now=T0)
        self.assertIsNone(tasks.claim(conn, now=T0 + timedelta(seconds=59)))
        self.assertEqual(tasks.claim(conn, now=T0 + timedelta(seconds=60))["id"], tid)

    def test_retry_schedule_then_failed(self):
        conn = db()
        tid = tasks.enqueue(conn, "k", {}, now=T0)
        now, waits = T0, []
        for _ in range(3):
            tasks.claim(conn, now=now)
            self.assertEqual(tasks.retry_or_fail(conn, tid, "boom", now=now), "queued")
            run_after = datetime.fromisoformat(tasks.get(conn, tid)["run_after"])
            waits.append(run_after - now)
            now = run_after
        tasks.claim(conn, now=now)
        self.assertEqual(tasks.retry_or_fail(conn, tid, "boom", now=now), "failed")
        self.assertEqual(waits, [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30)])
        self.assertEqual(tasks.get(conn, tid)["attempts"], 4)

    def test_finish_stores_result_and_model(self):
        conn = db()
        tid = tasks.enqueue(conn, "k", {}, now=T0)
        tasks.claim(conn, now=T0)
        tasks.finish(conn, tid, "hasil", "ag/gemini-3.8-flash-high", now=T0)
        task = tasks.get(conn, tid)
        self.assertEqual((task["status"], task["result"], task["model"]), ("done", "hasil", "ag/gemini-3.8-flash-high"))

    def test_requeue_running_on_start(self):
        conn = db()
        tid = tasks.enqueue(conn, "k", {}, now=T0)
        tasks.claim(conn, now=T0)  # worker died right after claiming
        self.assertEqual(tasks.requeue_running(conn), 1)
        self.assertEqual(tasks.claim(conn, now=T0)["id"], tid)

    def test_counts_failed_only_last_day(self):
        conn = db()
        old = tasks.enqueue(conn, "k", {}, now=T0)
        tasks.fail_now(conn, old, "x", now=T0)
        tasks.enqueue(conn, "k", {}, now=T0)
        running = tasks.enqueue(conn, "k", {}, now=T0 - timedelta(seconds=1))
        tasks.claim(conn, now=T0)
        self.assertEqual(tasks.counts(conn, now=T0), {"running": 1, "queued": 1, "failed": 1})
        self.assertEqual(tasks.counts(conn, now=T0 + timedelta(days=2))["failed"], 0)
        self.assertEqual(tasks.get(conn, running)["status"], "running")

    def test_recent_has_title_and_preview(self):
        conn = db()
        tid = tasks.enqueue(conn, "llm.prompt", {"title": "Riset"}, now=T0)
        tasks.claim(conn, now=T0)
        tasks.finish(conn, tid, "x" * 500, "m", now=T0)
        row = tasks.recent(conn)[0]
        self.assertEqual((row["title"], len(row["preview"])), ("Riset", 200))


if __name__ == "__main__":
    unittest.main()
