import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from connectors.google_auth import AuthError, TokenMissing
from hub import morning

NOW = datetime(2026, 10, 16, 0, 5, tzinfo=timezone.utc)  # 07:05 WIB
EVENTS = [{"id": "e1", "title": "Interview PT D", "start": "2026-10-16T07:50:00+07:00", "time": "07:50"},
          {"id": "e2", "title": "Rapat", "start": "2026-10-16T13:00:00+07:00", "time": "13:00"},
          {"id": "e3", "title": "Libur", "start": None, "time": None}]


class Morning(unittest.TestCase):
    def test_text_has_agenda_and_counts(self):
        with mock.patch("hub.collectors.jobs.collect", return_value={
                "new_matches": 3, "drafts": 0, "active": 12, "interview": 1, "followup_due": 2}), \
             mock.patch("hub.collectors.today.collect", return_value={"calendar": "ok", "items": [
                {"time": "10:00", "title": "Interview PT X", "kind": "event"},
                {"time": None, "title": "Follow-up PT C", "kind": "followup"}]}):
            text = morning.morning_text({}, NOW)
        self.assertIn("10:00 Interview PT X", text)
        self.assertIn("Follow-up PT C", text)
        self.assertIn("3 lowongan baru", text)

    def test_empty_day(self):
        with mock.patch("hub.collectors.jobs.collect", return_value={
                "new_matches": 0, "drafts": 0, "active": 0, "interview": 0, "followup_due": 0}), \
             mock.patch("hub.collectors.today.collect", return_value={"calendar": "off", "items": []}):
            self.assertIn("Tidak ada agenda", morning.morning_text({}, NOW))

    def test_soon_events_window(self):
        with mock.patch("connectors.gcal.list_events", return_value=EVENTS):
            events, err = morning.soon_events({}, NOW)
        self.assertEqual(([e["id"] for e in events], err), (["e1"], None))

    def test_soon_events_no_login_is_silent(self):
        with mock.patch("connectors.gcal.list_events", side_effect=TokenMissing("x")):
            self.assertEqual(morning.soon_events({}, NOW), ([], None))

    def test_soon_events_revoked_reports_error(self):
        with mock.patch("connectors.gcal.list_events", side_effect=AuthError("dicabut")):
            events, err = morning.soon_events({}, NOW)
        self.assertEqual((events, err), ([], "dicabut"))


if __name__ == "__main__":
    unittest.main()
