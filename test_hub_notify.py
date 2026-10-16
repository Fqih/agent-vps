import json
import unittest
import urllib.error
from unittest import mock

from hub import notify

ENV = {"NTFY_URL": "http://ntfy.test/", "NTFY_TOKEN": "tok",
       "TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1"}


class FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"{}"


class Publish(unittest.TestCase):
    def test_posts_json_with_token(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResp()) as op:
            ok = notify.publish(ENV, "jobs", "Lamar PT Ölçü 🎯", "isi", click="http://x")
        self.assertTrue(ok)
        req = op.call_args[0][0]
        self.assertEqual(req.full_url, "http://ntfy.test")
        self.assertEqual(req.get_header("Authorization"), "Bearer tok")
        self.assertEqual(json.loads(req.data.decode()), {
            "topic": "jobs", "title": "Lamar PT Ölçü 🎯", "message": "isi",
            "priority": 3, "click": "http://x"})

    def test_high_falls_back_to_telegram(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")), \
                mock.patch("tg.send") as send:
            self.assertFalse(notify.publish(ENV, "alerts", "VPS", "cv-bot down", "high"))
        send.assert_called_once()
        self.assertIn("cv-bot down", send.call_args[0][1])

    def test_default_failure_has_no_fallback(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("x")), \
                mock.patch("tg.send") as send:
            self.assertFalse(notify.publish(ENV, "tasks", "t", "m"))
        send.assert_not_called()

    def test_fallback_can_be_disabled(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("x")), \
                mock.patch("tg.send") as send:
            notify.publish(ENV, "alerts", "t", "m", "high", fallback=False)
        send.assert_not_called()

    def test_missing_url_never_raises(self):
        with mock.patch("tg.send"):
            self.assertFalse(notify.publish({}, "jobs", "t", "m"))


if __name__ == "__main__":
    unittest.main()
