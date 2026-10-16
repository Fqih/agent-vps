"""Worker against a fake 9router on localhost."""
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from hub import llm, tasks, worker

T0 = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)


class FakeRouter(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body["model"] == "good/model":
            out, code = {"choices": [{"message": {"content": "hasil riset"}}]}, 200
        else:
            out, code = {"error": {"message": f"[x/{body['model']}] [404]: not found"}}, 503
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class Worker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeRouter)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.ctx = {"env": {"STATUS_PUBLIC_URL": "http://hub.test", "STATUS_TOKEN": "s"},
                   "cfg": {"base_url": f"http://127.0.0.1:{cls.server.server_port}/v1", "api_key": "k"}}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        llm._dead.clear()
        self.db = tasks.connect(":memory:")

    def test_empty_queue(self):
        self.assertFalse(worker.run_once(self.db, self.ctx, now=T0))

    def test_done_with_fallback_and_notify(self):
        tid = tasks.enqueue(self.db, "llm.prompt", {"prompt": "riset", "title": "Riset PT X"}, now=T0)
        chains = {"fast": ["bad/model", "good/model"]}
        with mock.patch("hub.llm.load_chains", return_value=chains), mock.patch("hub.notify.publish") as pub:
            self.assertTrue(worker.run_once(self.db, self.ctx, now=T0))
        task = tasks.get(self.db, tid)
        self.assertEqual((task["status"], task["model"], task["result"]), ("done", "good/model", "hasil riset"))
        args, kwargs = pub.call_args
        self.assertEqual(args[1:3], ("tasks", "Selesai: Riset PT X"))
        self.assertEqual(kwargs["click"], f"http://hub.test/task/{tid}?token=s")

    def test_notify_false_stays_silent(self):
        tasks.enqueue(self.db, "llm.prompt", {"prompt": "x", "notify": False}, now=T0)
        with mock.patch("hub.llm.load_chains", return_value={"fast": ["good/model"]}), \
                mock.patch("hub.notify.publish") as pub:
            worker.run_once(self.db, self.ctx, now=T0)
        pub.assert_not_called()

    def test_retries_then_failed_notifies_once(self):
        tid = tasks.enqueue(self.db, "llm.prompt", {"prompt": "x", "title": "T"}, now=T0)
        now = T0
        with mock.patch("hub.llm.load_chains", return_value={"fast": ["bad/model"]}), \
                mock.patch("hub.notify.publish") as pub:
            for _ in range(4):
                self.assertTrue(worker.run_once(self.db, self.ctx, now=now))
                now += timedelta(hours=1)
        self.assertEqual(tasks.get(self.db, tid)["status"], "failed")
        pub.assert_called_once()
        self.assertEqual(pub.call_args[0][2], "Gagal: T")

    def test_unknown_kind_fails_without_retry(self):
        tid = tasks.enqueue(self.db, "nope", {}, now=T0)
        worker.run_once(self.db, self.ctx, now=T0)
        self.assertEqual(tasks.get(self.db, tid)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
