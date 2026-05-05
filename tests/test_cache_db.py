import os
import tempfile
import unittest
from unittest.mock import patch

from data.cache import CacheDB


class CacheDBTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(prefix="cache-db-", suffix=".json")
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_set_with_ttl_expires_after_deadline(self):
        cache = CacheDB(filepath=self.path)

        with patch("data.cache.time.time", return_value=1000):
            cache.set("k", {"v": 1}, ttl_seconds=10)

        with patch("data.cache.time.time", return_value=1005):
            self.assertEqual(cache.get("k"), {"v": 1})

        with patch("data.cache.time.time", return_value=1012):
            self.assertIsNone(cache.get("k"))

    def test_get_stale_returns_last_value_after_ttl_expired(self):
        cache = CacheDB(filepath=self.path)

        with patch("data.cache.time.time", return_value=2000):
            cache.set("k", {"v": 2}, ttl_seconds=5)

        with patch("data.cache.time.time", return_value=2010):
            self.assertIsNone(cache.get("k"))

        self.assertEqual(cache.get_stale("k"), {"v": 2})


if __name__ == "__main__":
    unittest.main()
