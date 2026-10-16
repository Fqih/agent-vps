"""The shipped .env.example must not turn comments into secret values."""
import unittest
from pathlib import Path
from unittest import mock

import digest


class EnvExample(unittest.TestCase):
    def test_blank_hub_keys_stay_blank(self):
        with mock.patch.object(digest, "ENV_FILES", [Path(__file__).with_name(".env.example")]), \
                mock.patch.dict("os.environ", {}, clear=True):
            env = digest.load_env()
        for key in ("NTFY_TOKEN", "STATUS_TOKEN", "STATUS_PUBLIC_URL"):
            self.assertEqual(env.get(key), "", key)


if __name__ == "__main__":
    unittest.main()
