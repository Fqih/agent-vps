"""Quota summary from 9router usage bodies (shapes copied from the live API)."""
import unittest
from datetime import datetime, timezone

from hub import quota

NOW = datetime(2026, 10, 16, 4, 0, tzinfo=timezone.utc)


def gemini(session, weekly, reset="2026-10-16T11:52:16.000Z"):
    return {"plan": "Antigravity", "quotas": {
        "claude-sonnet-4-6": {"used": 900, "total": 1000, "remainingPercentage": 10, "resetAt": reset},
        "gemini_session": {"used": 0, "total": 1000, "remainingPercentage": session, "resetAt": reset},
        "gemini_weekly": {"used": 0, "total": 1000, "remainingPercentage": weekly, "resetAt": "2026-10-23T06:52:17.000Z"}}}


CLAUDE = {"plan": "Claude Code", "quotas": {
    "session (5h)": {"used": 33, "total": 100, "remaining": 67, "remainingPercentage": 67, "resetAt": "2026-10-16T11:30:00.377Z"},
    "weekly (7d)": {"used": 28, "total": 100, "remaining": 72, "remainingPercentage": 72, "resetAt": "2026-10-21T22:00:00.377Z"}}}
CODEX = {"plan": "plus", "quotas": {
    "session": {"used": 3, "total": 100, "remaining": 97, "resetAt": "2026-10-16T11:23:28.000Z"},
    "weekly": {"used": 12, "total": 100, "remaining": 88, "resetAt": "2026-10-22T06:13:18.000Z"}}}


class Summarize(unittest.TestCase):
    def test_average_per_provider_and_soonest_reset(self):
        out = quota.summarize({"antigravity": [gemini(100, 90), gemini(50, 70, "2026-10-16T09:00:00.000Z")],
                               "claude": [CLAUDE], "codex": [CODEX]})
        self.assertEqual(out["gemini"], {"accounts": 2, "session": 75, "weekly": 80, "reset": "16:00"})
        self.assertEqual(out["claude"], {"accounts": 1, "session": 67, "weekly": 72, "reset": "18:30"})
        self.assertEqual(out["codex"], {"accounts": 1, "session": 97, "weekly": 88, "reset": "18:23"})

    def test_gemini_ignores_non_gemini_models(self):
        self.assertEqual(quota.summarize({"antigravity": [gemini(100, 100)]})["gemini"]["session"], 100)

    def test_missing_provider_is_absent(self):
        self.assertEqual(quota.summarize({"codex": [CODEX]}), {"codex": {"accounts": 1, "session": 97, "weekly": 88,
                                                                          "reset": "18:23"}})

    def test_unlimited_counts_as_full(self):
        body = {"quotas": {"session": {"unlimited": True}, "weekly": {"used": 50, "total": 100}}}
        self.assertEqual(quota.summarize({"codex": [body]})["codex"]["session"], 100)
        self.assertEqual(quota.summarize({"codex": [body]})["codex"]["weekly"], 50)


class Collect(unittest.TestCase):
    def test_returns_last_background_value(self):
        quota._state["value"] = {"codex": {"accounts": 1}}
        self.assertEqual(quota.collect({}, NOW), {"codex": {"accounts": 1}})

    def test_failed_refresh_keeps_last_good_value(self):
        quota._state["value"] = {"codex": {"accounts": 1}}
        quota.refresh_once({}, fetch=lambda ctx: (_ for _ in ()).throw(OSError("router down")))
        self.assertEqual(quota._state["value"], {"codex": {"accounts": 1}})


if __name__ == "__main__":
    unittest.main()
