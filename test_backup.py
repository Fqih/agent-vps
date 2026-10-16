"""backup.main: success marker and failure alerts."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import backup


class Main(unittest.TestCase):
    def run_backup(self, snapshot_error=None):
        dest = Path(tempfile.mkdtemp())
        with mock.patch.object(backup, "DEST", dest), \
                mock.patch.object(backup, "DBS", {"a": dest / "a.sqlite"}), \
                mock.patch.object(backup, "snapshot", side_effect=snapshot_error, return_value=dest / "a.gz"), \
                mock.patch.object(backup, "router_config", return_value=dest / "c.tar.gz"), \
                mock.patch("digest.load_env", return_value={}), \
                mock.patch("hub.notify.publish") as publish, \
                mock.patch("tg.send"):
            code = backup.main()
        return code, dest, publish

    def test_success_writes_marker(self):
        code, dest, publish = self.run_backup()
        self.assertEqual(code, 0)
        self.assertEqual([p.name for p in dest.glob("*/OK")], ["OK"])
        publish.assert_not_called()

    def test_failure_alerts_ntfy_without_marker(self):
        code, dest, publish = self.run_backup(snapshot_error=OSError("disk full"))
        self.assertEqual(code, 1)
        self.assertEqual(list(dest.glob("*/OK")), [])
        self.assertEqual((publish.call_args.args[1], publish.call_args.args[4]), ("alerts", "high"))


if __name__ == "__main__":
    unittest.main()
