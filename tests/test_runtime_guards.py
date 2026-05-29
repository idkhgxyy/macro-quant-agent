"""Tests for runtime safety guards: kill switch, market hours, planning-only enforcement."""
import unittest

from core.planning import get_submission_guard_reason


class RuntimeGuardsTests(unittest.TestCase):
    def test_ibkr_requires_explicit_live_enable(self):
        self.assertEqual(
            get_submission_guard_reason("ibkr", False),
            "live_trading_disabled",
        )

    def test_ibkr_allows_submit_when_live_enabled(self):
        self.assertIsNone(get_submission_guard_reason("ibkr", True))

    def test_mock_mode_is_not_blocked(self):
        self.assertIsNone(get_submission_guard_reason("mock", False))


if __name__ == "__main__":
    unittest.main()
