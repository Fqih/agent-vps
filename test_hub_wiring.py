"""Hub hooks inside infobot.scheduled and the status access log."""
import sqlite3
import threading
import unittest
import urllib.request
from datetime import datetime, timezone
from unittest import mock

import infobot
import monitor
import practice
import readlater
import tracker
from hub import status

TICK = datetime(2026, 10, 16, 0, 10, tzinfo=timezone.utc)  # 07:10 WIB
INFO = {"HC_PING_URL": "https://hc.test/ping", "TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}


def state_db():
    conn = sqlite3.connect(":memory:")
    for mod in (tracker, monitor, readlater, practice):
        mod.init(conn)
    return conn


class Scheduled(unittest.TestCase):
    def tick(self, db, soon=None, morning_text=None, at=TICK, alerts=(), send_error=None, delivered=True):
        soon = soon or mock.Mock(return_value=([], None))
        morning_text = morning_text or mock.Mock(return_value="agenda")
        with mock.patch.object(monitor, "now_utc", return_value=at), \
                mock.patch.object(monitor, "new_ssh_logins", return_value=([], 0)), \
                mock.patch.object(monitor, "run_checks", return_value={}), \
                mock.patch.object(monitor, "transitions", return_value=list(alerts)), \
                mock.patch.object(monitor, "check_url") as ping, \
                mock.patch.object(monitor, "domain_days_left", return_value=None), \
                mock.patch.object(infobot, "background"), \
                mock.patch("hub.morning.soon_events", soon), \
                mock.patch("hub.morning.morning_text", morning_text), \
                mock.patch("hub.notify.publish", return_value=delivered) as publish, \
                mock.patch("tg.send", side_effect=send_error):
            try:
                infobot.scheduled(db, INFO, INFO, {})
            except OSError:
                pass  # a Telegram outage may abort the tick; what matters is what reached ntfy
        return ping, publish

    def test_check_tick_records_vps_sample(self):
        db = state_db()
        with mock.patch("hub.collectors.vps.collect", return_value={"cpu": 5, "ram": 60, "disk": 22}):
            self.tick(db)
        self.assertEqual(db.execute("SELECT cpu, ram, disk FROM vps_samples").fetchall(), [(5, 60, 22)])

    def test_status_serves_quota(self):
        self.assertIn("quota", status.COLLECTORS)

    def test_monitor_alert_reaches_ntfy_when_telegram_fails(self):
        _, publish = self.tick(state_db(), alerts=["DOWN container:ntfy"], send_error=OSError("tg down"))
        self.assertIn("alerts", [c.args[1] for c in publish.call_args_list])

    def test_failed_morning_publish_is_retried(self):
        db = state_db()
        self.tick(db, delivered=False)
        self.assertNotEqual(tracker.kv_get(db, "morning_push"), "2026-10-16")

    def test_follow_up_goes_to_jobs_topic(self):
        db = state_db()
        jid = tracker.record(db, {"url": "https://x.test/1", "title": "Data Analyst", "company": "PT X",
                                  "location": "Jakarta"})
        db.execute("UPDATE jobs SET status = 'dilamar', next_remind = '2000-01-01' WHERE id = ?", (jid,))
        db.commit()
        noon = datetime(2026, 10, 16, 5, 0, tzinfo=timezone.utc)  # 12:00 WIB, inside DAYTIME
        _, publish = self.tick(db, at=noon)
        jobs = [c for c in publish.call_args_list if c.args[1] == "jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertIn("PT X", jobs[0].args[3])

    def test_calendar_crash_still_pings_healthcheck(self):
        ping, _ = self.tick(state_db(), soon=mock.Mock(side_effect=KeyError("refresh_token")))
        ping.assert_called_once_with("https://hc.test/ping")

    def test_morning_failure_is_retried_next_tick(self):
        db = state_db()
        self.tick(db, morning_text=mock.Mock(side_effect=sqlite3.OperationalError("database is locked")))
        self.assertNotEqual(tracker.kv_get(db, "morning_push"), "2026-10-16")
        _, publish = self.tick(db)
        topics = [c.args[1] for c in publish.call_args_list]
        self.assertIn("digest", topics)
        self.assertEqual(tracker.kv_get(db, "morning_push"), "2026-10-16")


class AccessLog(unittest.TestCase):
    def test_token_not_written_to_log(self):
        status._cache.clear()
        with mock.patch.object(status, "COLLECTORS", {}):
            server = status.make_server({"env": {"STATUS_TOKEN": "rahasia123"}}, port=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with self.assertLogs("hub.status", "INFO") as logs:
                    urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/status?token=rahasia123",
                                           timeout=5).read()
            finally:
                server.shutdown()
                server.server_close()
        text = "\n".join(logs.output)
        self.assertIn("/status", text)
        self.assertNotIn("rahasia123", text)


if __name__ == "__main__":
    unittest.main()
