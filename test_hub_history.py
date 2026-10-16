"""VPS samples for the widget line charts."""
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hub import history

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)


class History(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        history.init(self.db)

    def test_record_prunes_older_than_a_day(self):
        history.record(self.db, NOW - timedelta(hours=25), 1, 2, 3)
        history.record(self.db, NOW, 10, 20, 30)
        self.assertEqual(self.db.execute("SELECT cpu, ram, disk FROM vps_samples").fetchall(), [(10, 20, 30)])

    def test_series_window_oldest_first(self):
        for i in range(10):
            history.record(self.db, NOW - timedelta(minutes=5 * (9 - i)), i, 50 + i, 20)
        history.record(self.db, NOW - timedelta(hours=7), 99, 99, 99)  # outside the 6 h window
        out = history.series(self.db, NOW)
        self.assertEqual(out["cpu"], list(range(10)))
        self.assertEqual(out["ram"][-1], 59)

    def test_series_downsamples_to_points(self):
        for i in range(72):  # 6 h at 5 min
            history.record(self.db, NOW - timedelta(minutes=5 * (71 - i)), i, i, i)
        out = history.series(self.db, NOW, points=36)
        self.assertEqual(len(out["cpu"]), 36)
        self.assertEqual((out["cpu"][0], out["cpu"][-1]), (0, 71))

    def test_missing_table_reads_empty(self):
        self.assertEqual(history.series(sqlite3.connect(":memory:"), NOW), {"cpu": [], "ram": [], "disk": []})


if __name__ == "__main__":
    unittest.main()
