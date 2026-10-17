"""GitHub contribution calendar for the widget, parsed from the public HTML."""
import unittest
from datetime import date, datetime, timezone

from hub.collectors import github

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)  # Friday 16 Oct, 11:00 WIB


def day(i, d, level, tip):
    return (f'<td data-ix="{i}" style="width: 11px" data-date="{d}" id="contribution-day-component-{i}" '
            f'data-level="{level}" role="gridcell" class="ContributionCalendar-day"></td>'
            f'<tool-tip id="t{i}" for="contribution-day-component-{i}" class="sr-only">{tip}</tool-tip>')


# Sunday 4 Oct .. Friday 16 Oct 2026
HTML = "".join([
    day(0, "2026-10-04", 0, "No contributions on October 4th."),
    *[day(i, f"2026-10-{4 + i:02d}", 0, "No contributions on that day.") for i in range(1, 11)],
    day(11, "2026-10-15", 2, "5 contributions on October 15th."),
    day(12, "2026-10-16", 1, "1 contribution on October 16th."),
])


class Parse(unittest.TestCase):
    def test_counts_and_streak(self):
        out = github.parse(HTML, date(2026, 10, 16))
        self.assertEqual((out["total"], out["today"], out["streak"]), (6, 1, 2))

    def test_weeks_start_on_sunday_and_pad_future_days(self):
        weeks = github.parse(HTML, date(2026, 10, 16))["weeks"]
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0], [0] * 7)
        self.assertEqual(weeks[1], [0, 0, 0, 0, 2, 1, -1])  # Sun..Sat, Saturday is still ahead

    def test_streak_survives_quiet_today(self):
        html = HTML.replace("1 contribution on October 16th.", "No contributions on October 16th.") \
                   .replace('data-date="2026-10-16" id="contribution-day-component-12" data-level="1"',
                            'data-date="2026-10-16" id="contribution-day-component-12" data-level="0"')
        out = github.parse(html, date(2026, 10, 16))
        self.assertEqual((out["today"], out["streak"]), (0, 1))

    def test_page_without_calendar_raises(self):
        with self.assertRaises(ValueError):
            github.parse("<html>rate limited</html>", date(2026, 10, 16))


class Collect(unittest.TestCase):
    def setUp(self):
        github._cache.clear()

    def test_cached_for_an_hour(self):
        calls = []
        fetch = lambda user: calls.append(user) or HTML
        ctx = {"env": {"GITHUB_USER": "someone"}, "github_fetch": fetch}
        github.collect(ctx, NOW)
        out = github.collect(ctx, NOW)
        self.assertEqual((calls, out["user"]), (["someone"], "someone"))

    def test_failure_keeps_last_value(self):
        ctx = {"env": {}, "github_fetch": lambda user: HTML}
        first = github.collect(ctx, NOW)
        github._cache["at"] = 0  # expire
        ctx["github_fetch"] = lambda user: (_ for _ in ()).throw(OSError("down"))
        self.assertEqual(github.collect(ctx, NOW), first)


if __name__ == "__main__":
    unittest.main()
