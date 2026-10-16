import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from connectors import gcal, google_auth

T0 = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)


class FakeResp:
    def __init__(self, data: dict):
        self.data = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.data


class Token(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "google-token.json"

    def tearDown(self):
        self.dir.cleanup()

    def write(self, expiry: datetime):
        self.path.write_text(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r",
                                         "access_token": "old", "expiry": expiry.isoformat()}))

    def test_valid_token_needs_no_http(self):
        self.write(T0 + timedelta(minutes=30))
        with mock.patch("urllib.request.urlopen") as op:
            self.assertEqual(google_auth.access_token(self.path, now=T0), "old")
        op.assert_not_called()

    def test_refresh_near_expiry_and_save_private(self):
        self.write(T0 + timedelta(minutes=2))
        with mock.patch("urllib.request.urlopen", return_value=FakeResp({"access_token": "new", "expires_in": 3600})):
            self.assertEqual(google_auth.access_token(self.path, now=T0), "new")
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["refresh_token"], "r")
        self.assertEqual(datetime.fromisoformat(saved["expiry"]), T0 + timedelta(hours=1))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_invalid_grant_raises_auth_error(self):
        self.write(T0)
        err = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error": "invalid_grant"}'))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(google_auth.AuthError):
                google_auth.access_token(self.path, now=T0)

    def test_missing_file_is_token_missing(self):
        with self.assertRaises(google_auth.TokenMissing):
            google_auth.access_token(self.path, now=T0)


class Calendar(unittest.TestCase):
    def test_list_events_timed_and_all_day(self):
        items = {"items": [
            {"id": "e1", "summary": "Interview PT X", "start": {"dateTime": "2026-10-16T10:00:00+07:00"}},
            {"id": "e2", "summary": "Libur", "start": {"date": "2026-10-16"}},
            {"id": "e3", "start": {"dateTime": "2026-10-16T05:30:00Z"}}]}
        with mock.patch("urllib.request.urlopen", return_value=FakeResp(items)) as op:
            events = gcal.list_events(date(2026, 10, 16), token_fn=lambda: "tok")
        req = op.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer tok")
        self.assertIn("timeMin=2026-10-16T00%3A00%3A00%2B07%3A00", req.full_url)
        self.assertEqual(events, [
            {"id": "e1", "title": "Interview PT X", "start": "2026-10-16T10:00:00+07:00", "time": "10:00"},
            {"id": "e2", "title": "Libur", "start": None, "time": None},
            {"id": "e3", "title": "(tanpa judul)", "start": "2026-10-16T12:30:00+07:00", "time": "12:30"}])

    def test_create_event_posts_body(self):
        start = datetime(2026, 10, 17, 10, 0, tzinfo=gcal.WIB)
        with mock.patch("urllib.request.urlopen", return_value=FakeResp({"id": "new1"})) as op:
            eid = gcal.create_event("Interview", start, start + timedelta(hours=1), "Zoom", token_fn=lambda: "tok")
        req = op.call_args[0][0]
        self.assertEqual((eid, req.get_method()), ("new1", "POST"))
        self.assertEqual(json.loads(req.data.decode()), {
            "summary": "Interview", "description": "Zoom",
            "start": {"dateTime": "2026-10-17T10:00:00+07:00"},
            "end": {"dateTime": "2026-10-17T11:00:00+07:00"}})


if __name__ == "__main__":
    unittest.main()
