import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import monitor
import practice
import readlater
import tracker
import digest
from unittest import mock

import sources
from digest import WIB
from infobot import digest_missing, is_owner

NOW = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)
OWNER = 123456789


def db():
    conn = sqlite3.connect(":memory:")
    for mod in (tracker, monitor, readlater, practice):
        mod.init(conn)
    return conn


class Owner(unittest.TestCase):
    def msg(self, from_id, chat_id):
        return {"message": {"from": {"id": from_id}, "chat": {"id": chat_id}, "text": "/status"}}

    def test_only_owner_private_chat(self):
        self.assertTrue(is_owner(self.msg(OWNER, OWNER), OWNER))
        self.assertFalse(is_owner(self.msg(123, 123), OWNER))
        self.assertFalse(is_owner(self.msg(OWNER, -100999), OWNER))  # owner inside some group

    def test_callback_from_stranger_rejected(self):
        cq = {"callback_query": {"from": {"id": 123}, "message": {"chat": {"id": OWNER}}}}
        self.assertFalse(is_owner(cq, OWNER))
        cq["callback_query"]["from"]["id"] = OWNER
        self.assertTrue(is_owner(cq, OWNER))

    def test_other_update_types_rejected(self):
        self.assertFalse(is_owner({"edited_message": {}}, OWNER))


class Tracker(unittest.TestCase):
    def setUp(self):
        self.db = db()
        self.jid = tracker.record(self.db, {"url": "https://x/1", "title": "AI Engineer", "company": "Acme"})

    def test_record_is_idempotent(self):
        self.assertEqual(tracker.record(self.db, {"url": "https://x/1"}), self.jid)

    def test_apply_sets_reminder_and_fires_once(self):
        tracker.set_status(self.db, self.jid, "dilamar", NOW)
        self.assertEqual(tracker.due_reminders(self.db, NOW + timedelta(days=6)), [])
        due = tracker.due_reminders(self.db, NOW + timedelta(days=7, minutes=1))
        self.assertEqual([j["id"] for j in due], [self.jid])
        self.assertEqual(tracker.due_reminders(self.db, NOW + timedelta(days=7, minutes=2)), [])

    def test_closed_status_clears_reminder(self):
        tracker.set_status(self.db, self.jid, "dilamar", NOW)
        tracker.set_status(self.db, self.jid, "ditolak", NOW)
        self.assertEqual(tracker.due_reminders(self.db, NOW + timedelta(days=30)), [])

    def test_invalid_action_rejected(self):
        self.assertIsNone(tracker.set_status(self.db, self.jid, "hapus_semua"))
        self.assertIsNone(tracker.set_status(self.db, 999, "dilamar"))

    def test_card_buttons_follow_status(self):
        _, buttons = tracker.card(tracker.set_status(self.db, self.jid, "dilamar", NOW))
        self.assertIn(f"st:{self.jid}:interview", [b["callback_data"] for b in buttons[0]])
        _, buttons = tracker.card(tracker.set_status(self.db, self.jid, "offer", NOW))
        self.assertEqual(buttons, [])

    def test_list_and_recap_escape_html(self):
        jid = tracker.record(self.db, {"url": "https://x/2", "title": "<b>DS</b>"}, status="disimpan")
        self.assertIn(f"/j{jid} &lt;b&gt;DS&lt;/b&gt;", tracker.active_list(self.db))
        tracker.set_status(self.db, self.jid, "dilamar", NOW)
        self.assertIn("Minggu ini dilamar: <b>1</b>", tracker.recap(self.db, NOW + timedelta(days=1)))


class Feedback(unittest.TestCase):
    def setUp(self):
        self.db = db()
        self.good = tracker.record(self.db, {"url": "https://x/a", "title": "AI Engineer", "company": "Acme"})
        self.bad = tracker.record(self.db, {"url": "https://x/b", "title": "Sales AI", "company": "Spam"})
        tracker.record(self.db, {"url": "https://x/c", "title": "Ignored", "company": "Nobody"})

    def test_no_history_gives_empty_prompt(self):
        self.assertEqual(tracker.preferences(db()), "")

    def test_saved_and_thumbs_down_become_preferences(self):
        tracker.set_status(self.db, self.good, "disimpan", NOW)
        self.assertTrue(tracker.set_feedback(self.db, self.bad, -1))
        self.assertFalse(tracker.set_feedback(self.db, 999, -1))
        prefs = tracker.preferences(self.db)
        self.assertIn("Disukai:\n- AI Engineer @ Acme", prefs)
        self.assertIn("Tidak cocok:\n- Sales AI @ Spam", prefs)
        self.assertNotIn("Ignored", prefs)

    def test_recap_reports_hit_rate(self):
        tracker.set_status(self.db, self.good, "dilamar", NOW)
        tracker.set_feedback(self.db, self.bad, -1)
        self.assertIn("3 lowongan dikirim: 1 dipakai, 1 tidak cocok", tracker.recap(self.db, datetime.now(timezone.utc)))

    def test_picker_has_thumbs_down_row(self):
        import digest
        sent = {}
        with mock.patch.object(digest.tg, "send", lambda env, text, buttons=None: sent.update(b=buttons)):
            digest.send_job_picker(self.db, {}, [{"url": "https://x/a"}, {"url": "https://x/b"}])
        self.assertEqual([b["callback_data"] for b in sent["b"][1]], [f"nf:{self.good}", f"nf:{self.bad}"])


class Monitor(unittest.TestCase):
    def test_alert_after_two_failures_then_recovery(self):
        conn = db()
        down = {"site:a": (False, "timeout")}
        self.assertEqual(monitor.transitions(conn, down, NOW), [])
        self.assertEqual(monitor.transitions(conn, down, NOW + timedelta(minutes=5)), ["DOWN site:a: timeout"])
        self.assertEqual(monitor.transitions(conn, down, NOW + timedelta(minutes=10)), [])
        up = monitor.transitions(conn, {"site:a": (True, "HTTP 200")}, NOW + timedelta(minutes=25))
        self.assertEqual(up, ["PULIH site:a setelah 20 menit (HTTP 200)"])

    def test_single_blip_is_silent(self):
        conn = db()
        self.assertEqual(monitor.transitions(conn, {"s": (False, "x")}, NOW), [])
        self.assertEqual(monitor.transitions(conn, {"s": (True, "ok")}, NOW), [])

    def test_ssh_log_tail(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "auth.log"
            log.write_text("old Accepted publickey for root from 1.1.1.1 port 1\n")
            alerts, off = monitor.new_ssh_logins(-1, log)       # first run: skip history
            self.assertEqual(alerts, [])
            with open(log, "a") as fh:
                fh.write("sshd[1]: Accepted publickey for agent from 203.0.113.5 port 5 ssh2\n")
            alerts, off2 = monitor.new_ssh_logins(off, log)
            self.assertEqual(alerts, ["Login SSH: user agent dari 203.0.113.5 (publickey)"])
            log.write_text("")                                  # rotated
            self.assertEqual(monitor.new_ssh_logins(off2, log), ([], 0))


class Practice(unittest.TestCase):
    def setUp(self):
        self.db = db()
        self.orig = practice.chat_json

    def tearDown(self):
        practice.chat_json = self.orig

    def test_spacing(self):
        self.assertEqual(practice.next_due(9, NOW), (NOW + timedelta(days=14)).isoformat())
        self.assertEqual(practice.next_due(6, NOW), (NOW + timedelta(days=3)).isoformat())
        self.assertEqual(practice.next_due(2, NOW), (NOW + timedelta(days=1)).isoformat())

    def test_new_then_repeat_weak_answer(self):
        practice.chat_json = lambda prompt, cfg: {"question": "Apa itu overfitting?", "ideal": "model hafal"}
        qid, text = practice.ask(self.db, {}, NOW)
        self.assertIn("Soal baru", text)
        practice.chat_json = lambda prompt, cfg: {"score": 3, "feedback": "kurang contoh"}
        self.assertIn("Skor 3/10", practice.grade(self.db, qid, "tidak tahu", {}, NOW))
        qid2, text2 = practice.ask(self.db, {}, NOW + timedelta(days=1, minutes=1))
        self.assertEqual((qid2, "Ulangan" in text2), (qid, True))

    def test_score_clamped(self):
        practice.chat_json = lambda prompt, cfg: {"question": "q", "ideal": "i"}
        qid, _ = practice.ask(self.db, {}, NOW)
        practice.chat_json = lambda prompt, cfg: {"score": 99, "feedback": ""}
        self.assertIn("Skor 10/10", practice.grade(self.db, qid, "a", {}, NOW))


class ReadLater(unittest.TestCase):
    def test_first_url(self):
        self.assertEqual(readlater.first_url("baca ini https://a.com/x?y=1)."), "https://a.com/x?y=1")
        self.assertIsNone(readlater.first_url("halo"))

    def test_save_done_and_recap(self):
        conn = db()
        rid = readlater.save(conn, "https://a.com", "<Judul>", "- poin")
        self.assertIn("&lt;Judul&gt;", readlater.unread(conn))
        self.assertTrue(readlater.mark_done(conn, rid))
        self.assertIn("Tidak ada bacaan", readlater.unread(conn))
        self.assertIn("1 disimpan, 0 belum dibaca", readlater.weekly_recap(conn, datetime.now(timezone.utc)))
        self.assertFalse(readlater.mark_done(conn, 999))


class Domain(unittest.TestCase):
    def test_expiry_days(self):
        rdap = {"events": [{"eventAction": "registration", "eventDate": "2024-01-01T00:00:00Z"},
                           {"eventAction": "expiration", "eventDate": "2026-11-08T03:00:00Z"}]}
        self.assertEqual(monitor.expiry_days(rdap, NOW), 30)
        self.assertIsNone(monitor.expiry_days({}, NOW))


class SharedDb(unittest.TestCase):
    def test_digest_does_not_hold_write_lock(self):
        with tempfile.TemporaryDirectory() as d:
            orig, digest.DB_PATH = digest.DB_PATH, Path(d) / "s.sqlite"
            try:
                db = digest.open_db()
                self.assertFalse(db.in_transaction)
                other = sqlite3.connect(digest.DB_PATH, timeout=0)
                other.execute("CREATE TABLE t (x)")
                other.commit()                          # infobot write must not block
            finally:
                digest.DB_PATH = orig


class DigestWatch(unittest.TestCase):
    def test_alert_only_after_deadline_when_not_sent(self):
        conn = db()
        day = datetime(2026, 10, 10, 7, 30, tzinfo=WIB)
        self.assertFalse(digest_missing(conn, day))
        self.assertTrue(digest_missing(conn, day.replace(minute=50)))
        tracker.kv_set(conn, "digest_sent", "2026-10-10")
        self.assertFalse(digest_missing(conn, day.replace(minute=50)))
        self.assertTrue(digest_missing(conn, day + timedelta(days=1, minutes=20)))


class Fetch(unittest.TestCase):
    def resp(self):
        r = mock.MagicMock()
        r.__enter__.return_value.read.return_value = b"ok"
        return r

    @mock.patch.object(sources, "RETRY_DELAY", 0)
    def test_retries_timeout_once(self):
        with mock.patch("urllib.request.urlopen", side_effect=[TimeoutError("read timed out"), self.resp()]) as op:
            self.assertEqual(sources.get("https://x"), b"ok")
        self.assertEqual(op.call_count, 2)

    @mock.patch.object(sources, "RETRY_DELAY", 0)
    def test_http_error_not_retried(self):
        err = sources.urllib.error.HTTPError("https://x", 403, "no", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err) as op:
            self.assertRaises(sources.urllib.error.HTTPError, sources.get, "https://x")
        self.assertEqual(op.call_count, 1)


if __name__ == "__main__":
    unittest.main()
