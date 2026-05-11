import os
import unittest
from urllib.parse import urlparse

from dashboard.server import is_dashboard_authorized


class DashboardAuthTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("DASHBOARD_TOKEN")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DASHBOARD_TOKEN", None)
        else:
            os.environ["DASHBOARD_TOKEN"] = self._old

    def test_auth_disabled_allows_requests(self):
        os.environ.pop("DASHBOARD_TOKEN", None)
        self.assertTrue(is_dashboard_authorized(urlparse("/api/ping"), {}))

    def test_query_token_is_accepted(self):
        os.environ["DASHBOARD_TOKEN"] = "secret"
        self.assertTrue(is_dashboard_authorized(urlparse("/api/ping?token=secret"), {}))
        self.assertFalse(is_dashboard_authorized(urlparse("/api/ping?token=wrong"), {}))

    def test_header_token_is_accepted(self):
        os.environ["DASHBOARD_TOKEN"] = "secret"
        headers = {"X-Dashboard-Token": "secret"}
        self.assertTrue(is_dashboard_authorized(urlparse("/api/ping"), headers))

    def test_bearer_token_is_accepted(self):
        os.environ["DASHBOARD_TOKEN"] = "secret"
        headers = {"Authorization": "Bearer secret"}
        self.assertTrue(is_dashboard_authorized(urlparse("/api/ping"), headers))
        self.assertFalse(is_dashboard_authorized(urlparse("/api/ping"), {"Authorization": "Bearer wrong"}))


if __name__ == "__main__":
    unittest.main()
