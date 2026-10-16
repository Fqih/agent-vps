import io
import json
import os
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock

from hub import llm

T0 = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)
CFG = {"base_url": "http://router.test/v1", "api_key": "k"}
CHAINS = {"fast": ["a/dead", "b/ok"], "solo": ["a/dead"]}


class FakeResp:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def http_error(code: int, body: str):
    return urllib.error.HTTPError("http://router.test", code, "err", {}, io.BytesIO(body.encode()))


def opener(answers: dict, calls: list):
    def fake(req, timeout=None):
        model = json.loads(req.data.decode())["model"]
        calls.append(model)
        answer = answers[model]
        if isinstance(answer, Exception):
            raise answer
        return FakeResp(json.dumps({"choices": [{"message": {"content": answer}}]}).encode())
    return fake


class Chat(unittest.TestCase):
    def setUp(self):
        llm._dead.clear()

    def run_chat(self, answers, chain="fast", now=T0):
        calls = []
        with mock.patch("urllib.request.urlopen", side_effect=opener(answers, calls)):
            result = llm.chat(chain, [{"role": "user", "content": "hi"}], CFG, chains=CHAINS, now=now)
        return result, calls

    def test_falls_back_to_next_model(self):
        result, calls = self.run_chat({"a/dead": http_error(500, "boom"), "b/ok": " hasil "})
        self.assertEqual(result, ("hasil", "b/ok"))
        self.assertEqual(calls, ["a/dead", "b/ok"])

    def test_wrapped_404_marks_dead(self):
        wrapped = http_error(503, '{"error":{"message":"[antigravity/x] [404]: Requested entity was not found"}}')
        self.run_chat({"a/dead": wrapped, "b/ok": "x"})
        _, calls = self.run_chat({"a/dead": wrapped, "b/ok": "x"}, now=T0 + timedelta(hours=1))
        self.assertEqual(calls, ["b/ok"])

    def test_dead_model_revives_after_six_hours(self):
        self.run_chat({"a/dead": http_error(404, "nf"), "b/ok": "x"})
        _, calls = self.run_chat({"a/dead": "back", "b/ok": "x"}, now=T0 + timedelta(hours=6, seconds=1))
        self.assertEqual(calls, ["a/dead"])

    def test_plain_500_is_not_cached(self):
        self.run_chat({"a/dead": http_error(500, "boom"), "b/ok": "x"})
        _, calls = self.run_chat({"a/dead": "ok now", "b/ok": "x"}, now=T0 + timedelta(minutes=1))
        self.assertEqual(calls, ["a/dead"])

    def test_empty_answer_tries_next(self):
        result, _ = self.run_chat({"a/dead": "   ", "b/ok": "isi"})
        self.assertEqual(result, ("isi", "b/ok"))

    def test_all_failed_raises(self):
        with self.assertRaises(llm.ChainFailed):
            self.run_chat({"a/dead": urllib.error.URLError("refused")}, chain="solo")

    def test_request_shape(self):
        calls, seen = [], []

        def fake(req, timeout=None):
            seen.append(req)
            return opener({"a/dead": "x"}, calls)(req, timeout)
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            llm.chat("solo", [{"role": "user", "content": "hi"}], CFG, chains=CHAINS, now=T0)
        self.assertEqual(seen[0].full_url, "http://router.test/v1/chat/completions")
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer k")
        self.assertFalse(json.loads(seen[0].data.decode())["stream"])

    def test_weekly_digest_default_avoids_claude_subscription(self):
        import importlib
        import digest
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DIGEST_WEEKLY_MODELS", None)
            models = importlib.reload(digest).WEEKLY_MODELS
        self.assertFalse(any(m.startswith("cc/") for m in models))

    def test_shipped_chains_avoid_claude_subscription(self):
        chains = llm.load_chains()
        self.assertEqual(set(chains), {"bulk", "fast", "heavy"})
        for models in chains.values():
            self.assertFalse(any(m.startswith("cc/") for m in models))
        self.assertFalse(any("claude" in m for m in chains["fast"] + chains["heavy"]))


if __name__ == "__main__":
    unittest.main()
