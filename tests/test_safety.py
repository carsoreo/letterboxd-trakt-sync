import json
import os
import stat
import tempfile
import unittest

from lbtrakt import letterboxd
from lbtrakt.__main__ import save_state


class Safety(unittest.TestCase):
    def test_bad_usernames_rejected_before_any_request(self):
        for name in ["", "../x", "a/b", "user?x=1", "name with space", "x" * 31]:
            with self.assertRaises(ValueError):
                letterboxd.fetch_rss(name)

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_state_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            save_state(path, {"trakt_tokens": {"access_token": "x"}})
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["trakt_tokens"]["access_token"], "x")
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
