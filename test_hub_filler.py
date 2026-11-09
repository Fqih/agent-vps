"""Gemini quota filler: when to add work, what to add first, and the fill.* handlers."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import practice
import readlater
import tracker
from hub import filler, fillwork, tasks, worker

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc)
AT = (NOW - timedelta(minutes=5)).isoformat()
ROOM = {"accounts": 12, "session": 90, "weekly": 80, "at": AT}


def state_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    tracker.init(db)
    readlater.init(db)
    practice.init(db)
    return db


def add_job(db, url, created, feedback=None):
    db.execute("INSERT INTO jobs (url, title, company, location, status, created_at, feedback) "
               "VALUES (?, 'Data Scientist', 'PT A', 'Jakarta', 'baru', ?, ?)", (url, created.isoformat(), feedback))
    db.commit()


class Room(unittest.TestCase):
    def test_above_reserve(self):
        self.assertTrue(filler.has_room(ROOM, NOW))

    def test_session_at_reserve(self):
        self.assertFalse(filler.has_room({"session": filler.RESERVE, "weekly": 80, "at": AT}, NOW))

    def test_weekly_low(self):
        self.assertFalse(filler.has_room({"session": 90, "weekly": 10, "at": AT}, NOW))

    def test_free_tier_has_only_weekly(self):
        self.assertTrue(filler.has_room({"session": None, "weekly": 60, "at": AT}, NOW))

    def test_stale_reading_means_no(self):
        old = (NOW - filler.QUOTA_MAX_AGE - timedelta(minutes=1)).isoformat()
        self.assertFalse(filler.has_room(dict(ROOM, at=old), NOW))

    def test_unknown_quota_means_no(self):
        for q in (None, {}, {"error": "x"}, {"loading": True}, {"session": 90, "weekly": 90},
                  {"session": None, "weekly": None, "at": AT}):
            self.assertFalse(filler.has_room(q, NOW), q)

    def test_status_down_means_no(self):
        with mock.patch("hub.filler.gemini_quota", side_effect=OSError("refused")):
            self.assertEqual(filler.fill(tasks.connect(":memory:"), {"env": {}}, NOW), 0)


class Fill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "state.sqlite"
        self.state = state_db(self.state_path)
        self.db = tasks.connect(":memory:")
        self.ctx = {"env": {}, "state_db": self.state_path}
        patcher = mock.patch("hub.filler.github_candidates", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.state.close()
        self.tmp.cleanup()

    def kinds(self):
        return [t["kind"] for t in (tasks.get(self.db, r[0]) for r in self.db.execute("SELECT id FROM tasks ORDER BY id"))]

    def test_no_room_adds_nothing(self):
        add_job(self.state, "u1", NOW)
        self.assertEqual(filler.fill(self.db, self.ctx, NOW, quota=dict(ROOM, session=5)), 0)

    def test_jobs_first_then_questions(self):
        add_job(self.state, "u1", NOW - timedelta(days=1))
        add_job(self.state, "old", NOW - timedelta(days=30))
        add_job(self.state, "disliked", NOW, feedback=-1)
        self.assertEqual(filler.fill(self.db, self.ctx, NOW, quota=ROOM), filler.MAX_QUEUED)
        self.assertEqual(self.kinds(), ["fill.job"] + ["fill.question"] * (filler.MAX_QUEUED - 1))
        task = tasks.get(self.db, 1)
        self.assertEqual((task["chain"], task["payload"]["notify"]), ("gemini", False))

    def test_queue_full_adds_nothing(self):
        for _ in range(filler.MAX_QUEUED):
            tasks.enqueue(self.db, "llm.prompt", {"prompt": "x"}, now=NOW)
        self.assertEqual(filler.fill(self.db, self.ctx, NOW, quota=ROOM), 0)

    def test_done_job_is_not_added_again(self):
        add_job(self.state, "u1", NOW)
        filler.fill(self.db, self.ctx, NOW, quota=ROOM)
        self.db.execute("UPDATE tasks SET status = 'done'")
        filler.fill(self.db, self.ctx, NOW, quota=ROOM)
        self.assertEqual(self.kinds().count("fill.job"), 1)

    def test_reads_before_questions(self):
        readlater.save(self.state, "https://a.test/x", "Artikel", "- poin")
        filler.fill(self.db, self.ctx, NOW, quota=ROOM)
        self.assertEqual(self.kinds()[0], "fill.read")

    def test_question_bank_full(self):
        for i in range(filler.QUESTION_BANK_MAX):
            self.state.execute("INSERT INTO questions (topic, question, source, created_at) VALUES ('SQL', ?, 'bank', ?)",
                               (f"q{i}", NOW.isoformat()))
        self.state.commit()
        self.assertEqual(filler.fill(self.db, self.ctx, NOW, quota=ROOM), 0)

    def test_github_candidates_priority(self):
        with mock.patch("hub.filler.github_candidates",
                        return_value=[("fill.review", {"repo": "Fqih/x", "sha": "abc", "title": "Review"}, "fill:gh:abc")]):
            filler.fill(self.db, self.ctx, NOW, quota=ROOM)
        self.assertEqual(self.kinds()[0], "fill.review")


class GitHub(unittest.TestCase):
    def test_recent_commits_become_reviews(self):
        pushed = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        replies = {
            "/users/Fqih/repos?sort=pushed&per_page=10": [
                {"full_name": "Fqih/a", "pushed_at": pushed, "fork": False},
                {"full_name": "Fqih/old", "pushed_at": "2026-01-01T00:00:00Z", "fork": False}],
            "/repos/Fqih/a/commits?since=2026-11-02T03:00:00Z&per_page=10": [
                {"sha": "abc123", "commit": {"message": "fix: x\n\nbody"}, "parents": [{}]},
                {"sha": "merge1", "commit": {"message": "Merge"}, "parents": [{}, {}]}],
        }
        filler._github_cache.clear()
        out = filler.github_candidates({}, NOW, api=lambda path, env: replies[path])
        self.assertEqual([(k, p["sha"], d) for k, p, d in out], [("fill.review", "abc123", "fill:gh:abc123")])
        self.assertEqual(out[0][1]["title"], "Review Fqih/a: fix: x")

    def test_broken_repo_does_not_hide_others(self):
        pushed = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")

        def api(path, env):
            if path.startswith("/users/"):
                return [{"full_name": "Fqih/empty", "pushed_at": pushed}, {"full_name": "Fqih/b", "pushed_at": pushed},
                        {"full_name": "Fqih/new", "pushed_at": None}]
            if "empty" in path:
                raise OSError("409 Git Repository is empty")
            return [{"sha": "s1", "commit": {"message": ""}, "parents": [{}]}]
        filler._github_cache.clear()
        out = filler.github_candidates({}, NOW, api=api)
        self.assertEqual([(p["repo"], p["title"]) for _, p, _ in out], [("Fqih/b", "Review Fqih/b: ")])

    def test_api_error_gives_nothing(self):
        filler._github_cache.clear()

        def broken(path, env):
            raise OSError("rate limited")
        self.assertEqual(filler.github_candidates({}, NOW, api=broken), [])


class Handlers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "state.sqlite"
        state_db(self.state_path).close()
        self.ctx = {"env": {}, "cfg": {}, "state_db": self.state_path}

    def tearDown(self):
        self.tmp.cleanup()

    def test_question_goes_to_bank(self):
        task = {"payload": {"topic": "SQL"}, "chain": "gemini"}
        with mock.patch("hub.llm.chat", return_value=('{"question": "Apa itu JOIN?", "ideal": "..."}', "ag/g")):
            _, model = fillwork.question(task, self.ctx)
        self.assertEqual(model, "ag/g")
        with sqlite3.connect(str(self.state_path)) as db:
            row = db.execute("SELECT topic, question, score, due FROM questions").fetchone()
        self.assertEqual(row, ("SQL", "Apa itu JOIN?", None, None))
        with sqlite3.connect(str(self.state_path)) as db:
            self.assertEqual(db.execute("SELECT source FROM questions").fetchone(), ("bank",))

    def test_question_without_text_fails(self):
        with mock.patch("hub.llm.chat", return_value=("{}", "ag/g")), self.assertRaises(ValueError):
            fillwork.question({"payload": {"topic": "SQL"}, "chain": "gemini"}, self.ctx)

    def test_job_result_starts_with_score(self):
        job = {"job_id": 1, "title": "Data Scientist", "company": "PT A", "location": "Jakarta", "url": "https://j.test"}
        answer = '{"score": 82, "alasan": "cocok", "gap": "Spark", "perusahaan": "fintech", "cover_letter": "Halo"}'
        with mock.patch("brief.job_page_text", return_value="isi"), \
             mock.patch("hub.llm.chat", return_value=(answer, "ag/g")):
            text, _ = fillwork.job({"payload": job, "chain": "gemini"}, self.ctx)
        self.assertTrue(text.startswith("Skor: 82/100"))
        self.assertIn("Halo", text)

    def test_job_score_with_suffix(self):
        job = {"title": "x", "url": "https://j.test"}
        with mock.patch("brief.job_page_text", return_value=""), \
             mock.patch("hub.llm.chat", return_value=('{"score": "85/100"}', "ag/g")):
            text, _ = fillwork.job({"payload": job, "chain": "gemini"}, self.ctx)
        self.assertTrue(text.startswith("Skor: 85/100"))

    def test_review_reads_the_diff(self):
        with mock.patch("hub.fillwork.fetch_diff", return_value="diff --git a/x b/x"), \
             mock.patch("hub.llm.chat", return_value=("Tidak ada temuan.", "ag/g")) as chat:
            text, _ = fillwork.review({"payload": {"repo": "Fqih/a", "sha": "abc"}, "chain": "gemini"}, self.ctx)
        self.assertEqual(text, "Tidak ada temuan.")
        self.assertIn("diff --git", chat.call_args[0][1][-1]["content"])


class Summary(unittest.TestCase):
    def test_line_counts_and_best_job(self):
        db = tasks.connect(":memory:")
        for kind, payload, result in [
                ("fill.job", {"title": "Nilai: DS @ PT A"}, "Skor: 85/100\n..."),
                ("fill.job", {"title": "Nilai: DA @ PT B"}, "Skor: 40/100\n..."),
                ("fill.question", {"title": "Soal SQL"}, "ok")]:
            tid = tasks.enqueue(db, kind, payload, chain="gemini", now=NOW - timedelta(hours=2))
            tasks.finish(db, tid, result, "ag/g", now=NOW - timedelta(hours=1))
        line = filler.summary(db, NOW - timedelta(days=1))
        self.assertIn("3 tugas", line)
        self.assertIn("DS @ PT A (85)", line)

    def test_nothing_done(self):
        self.assertIsNone(filler.summary(tasks.connect(":memory:"), NOW - timedelta(days=1)))


class Counts(unittest.TestCase):
    def test_filler_failures_stay_off_the_widget(self):
        db = tasks.connect(":memory:")
        for kind in ("fill.read", "llm.prompt"):
            tasks.fail_now(db, tasks.enqueue(db, kind, {"title": kind}, now=NOW), "x", now=NOW)
        self.assertEqual(tasks.counts(db, NOW)["failed"], 1)
        self.assertEqual([t["kind"] for t in tasks.recent(db, skip_filler=True)], ["llm.prompt"])


class Worker(unittest.TestCase):
    def test_failed_filler_task_is_quiet(self):
        db = tasks.connect(":memory:")
        tid = tasks.enqueue(db, "fill.question", {"topic": "SQL", "notify": False}, chain="gemini", now=NOW)
        db.execute("UPDATE tasks SET attempts = ? WHERE id = ?", (len(tasks.RETRY_DELAYS), tid))
        with mock.patch.dict("hub.handlers.HANDLERS", {"fill.question": mock.Mock(side_effect=ValueError("x"))}), \
             mock.patch("hub.notify.publish") as pub:
            worker.run_once(db, {"env": {}}, now=NOW)
        self.assertEqual(tasks.get(db, tid)["status"], "failed")
        pub.assert_not_called()


class PracticeBank(unittest.TestCase):
    def test_bank_question_used_before_new_one(self):
        db = sqlite3.connect(":memory:")
        practice.init(db)
        db.execute("INSERT INTO questions (topic, question, created_at) VALUES ('SQL', 'Lama di-skip', ?)",
                   (NOW.isoformat(),))
        db.execute("INSERT INTO questions (topic, question, source, created_at) VALUES ('SQL', 'Apa itu JOIN?', 'bank', ?)",
                   (NOW.isoformat(),))
        with mock.patch("practice.chat_json") as chat:
            qid, text = practice.ask(db, {}, NOW)
        chat.assert_not_called()
        self.assertIn("Apa itu JOIN?", text)
        self.assertIsNotNone(db.execute("SELECT due FROM questions WHERE id = ?", (qid,)).fetchone()[0])
        self.assertIsNone(practice.bank_question(db, NOW))  # served once, and the old skipped one never


if __name__ == "__main__":
    unittest.main()
