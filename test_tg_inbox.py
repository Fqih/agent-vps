"""Images the owner sends to a bot are saved on the VPS for review."""
import os
import tempfile
import unittest
from pathlib import Path

import infobot
import tg
from unittest import mock

ENV = {"TELEGRAM_BOT_TOKEN": "x"}


class SaveImage(unittest.TestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp())
        self.calls = []

    def call(self, env, method, **payload):
        self.calls.append((method, payload))
        return {"ok": True, "result": {"file_path": "photos/file_9.jpg", "file_size": 3}}

    def download(self, url):
        self.calls.append(("download", url))
        return b"img"

    def test_largest_photo_saved_private(self):
        msg = {"message_id": 5, "photo": [{"file_id": "small"}, {"file_id": "big"}]}
        path = tg.save_image(ENV, msg, self.dest, call=self.call, download=self.download)
        self.assertEqual(self.calls[0], ("getFile", {"file_id": "big"}))
        self.assertEqual((path.read_bytes(), path.suffix, os.stat(path).st_mode & 0o777), (b"img", ".jpg", 0o600))

    def test_image_document_saved(self):
        msg = {"message_id": 6, "document": {"file_id": "d", "mime_type": "image/png", "file_name": "ss.png"}}
        self.assertIsNotNone(tg.save_image(ENV, msg, self.dest, call=self.call, download=self.download))

    def test_non_image_ignored(self):
        msg = {"message_id": 7, "document": {"file_id": "d", "mime_type": "application/zip"}}
        self.assertIsNone(tg.save_image(ENV, msg, self.dest, call=self.call, download=self.download))
        self.assertEqual(self.calls, [])

    def test_oversized_refused(self):
        big = lambda env, method, **p: {"ok": True, "result": {"file_path": "p.jpg", "file_size": tg.MAX_IMAGE + 1}}
        with self.assertRaises(ValueError):
            tg.save_image(ENV, {"message_id": 8, "photo": [{"file_id": "b"}]}, self.dest, call=big,
                          download=self.download)


class OwnerImage(unittest.TestCase):
    def test_saved_image_is_confirmed(self):
        with mock.patch("tg.save_image", return_value=Path("/x/20261017-1.jpg")), mock.patch("tg.send") as send:
            self.assertTrue(infobot.save_owner_image(ENV, {"photo": [{"file_id": "a"}]}))
        self.assertIn("20261017-1.jpg", send.call_args.args[1])

    def test_failure_is_reported_not_raised(self):
        with mock.patch("tg.save_image", side_effect=ValueError("too big")), mock.patch("tg.send") as send:
            self.assertTrue(infobot.save_owner_image(ENV, {"photo": [{"file_id": "a"}]}))
        self.assertIn("gagal", send.call_args.args[1])

    def test_non_image_not_handled(self):
        with mock.patch("tg.save_image", return_value=None), mock.patch("tg.send") as send:
            self.assertFalse(infobot.save_owner_image(ENV, {"sticker": {}}))
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
