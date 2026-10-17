"""Agenda pushed by the phone app (read from the phone's own calendars)."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from connectors import phonecal

NOW = datetime(2026, 10, 17, 2, 0, tzinfo=timezone.utc)  # 09:00 WIB
PAYLOAD = {"events": [
    {"id": "7:1", "title": "Standup", "start": "2026-10-17T10:00:00+07:00", "date": "2026-10-17", "all_day": False},
    {"id": "8:1", "title": "Libur", "start": None, "date": "2026-10-17", "all_day": True},
    {"id": "9:1", "title": "Pagi", "start": "2026-10-17T08:30:00+07:00", "date": "2026-10-17", "all_day": False},
    {"id": "10:1", "title": "Besok", "start": "2026-10-18T09:00:00+07:00", "date": "2026-10-18", "all_day": False},
]}


class Store(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "phone-agenda.json"

    def test_events_for_one_day_sorted_all_day_first(self):
        phonecal.store(self.path, PAYLOAD, NOW)
        self.assertEqual(phonecal.list_events(self.path, date(2026, 10, 17)), [
            {"id": "8:1", "title": "Libur", "start": None, "time": None},
            {"id": "9:1", "title": "Pagi", "start": "2026-10-17T08:30:00+07:00", "time": "08:30"},
            {"id": "7:1", "title": "Standup", "start": "2026-10-17T10:00:00+07:00", "time": "10:00"}])
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_bad_payload_rejected_and_old_data_kept(self):
        phonecal.store(self.path, PAYLOAD, NOW)
        bad = [{"events": "x"}, {"events": [{"title": 5}]}, [],
               {"events": [{"id": "1", "title": "t", "start": "2026-10-17T10:00:00", "date": "2026-10-17"}]},
               {"events": [{"id": "1", "title": "t", "start": None, "date": "kemarin", "all_day": True}]},
               {"events": [PAYLOAD["events"][0]] * (phonecal.MAX_EVENTS + 1)}]
        for payload in bad:
            with self.assertRaises(ValueError, msg=payload):
                phonecal.store(self.path, payload, NOW)
        self.assertEqual(len(phonecal.list_events(self.path, date(2026, 10, 17))), 3)

    def test_long_title_is_cut(self):
        phonecal.store(self.path, {"events": [{**PAYLOAD["events"][0], "title": "x" * 500}]}, NOW)
        self.assertEqual(len(phonecal.list_events(self.path, date(2026, 10, 17))[0]["title"]), 200)

    def test_state_fresh_stale_missing(self):
        self.assertIsNone(phonecal.state(self.path, NOW))
        phonecal.store(self.path, PAYLOAD, NOW)
        self.assertEqual(phonecal.state(self.path, NOW + timedelta(hours=3)), "hp · 09:00")
        self.assertTrue(phonecal.state(self.path, NOW + timedelta(hours=25)).startswith("error"))


if __name__ == "__main__":
    unittest.main()
