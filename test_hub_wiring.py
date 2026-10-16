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
    def tick(self, db, soon=None, morning_text=None):
        soon = soon or mock.Mock(return_value=([], None))
        morning_text = morning_text or mock.Mock(return_value="agenda")
        with mock.patch.object(monitor, "now_utc", return_value=TICK), \
                mock.patch.object(monitor, "new_ssh_logins", return_value=([], 0)), \
                mock.patch.object(monitor, "run_checks", return_value={}), \
                mock.patch.object(monitor, "check_url") as ping, \
                mock.patch("hub.morning.soon_events", soon), \
                mock.patch("hub.morning.morning_text", morning_text), \
                mock.patch("hub.notify.publish") as publish, \
                mock.patch("tg.send"):
            infobot.scheduled(db, INFO, INFO, {})
        return ping, publish

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
