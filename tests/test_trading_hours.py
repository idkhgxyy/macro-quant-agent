import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.trading_hours import get_market_session


NY = "America/New_York"


class TradingHoursTests(unittest.TestCase):
    def test_weekend_is_closed(self):
        now = datetime(2026, 5, 2, 10, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "closed")
        self.assertEqual(session["session_reason"], "weekend")
        self.assertFalse(session["can_generate_plan"])

    def test_good_friday_is_holiday(self):
        now = datetime(2026, 4, 3, 10, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "closed")
        self.assertEqual(session["session_reason"], "holiday")
        self.assertEqual(session["holiday_name"], "good_friday")

    def test_pre_market_is_planning_only(self):
        now = datetime(2026, 4, 30, 8, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "planning_only")
        self.assertEqual(session["session_reason"], "pre_market")
        self.assertTrue(session["can_generate_plan"])
        self.assertFalse(session["can_place_orders"])

    def test_half_day_uses_early_close(self):
        now = datetime(2026, 11, 27, 12, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "open")
        self.assertTrue(session["is_half_day"])
        self.assertEqual(session["effective_rth_end"], "13:00")

    def test_after_early_close_is_planning_only(self):
        now = datetime(2026, 11, 27, 14, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "planning_only")
        self.assertEqual(session["session_reason"], "after_early_close")

    def test_observed_new_year_can_fall_in_previous_year(self):
        now = datetime(2021, 12, 31, 10, 0, tzinfo=ZoneInfo(NY))
        session = get_market_session(now, NY, "09:30", "16:00", "13:00")
        self.assertEqual(session["market_state"], "closed")
        self.assertEqual(session["holiday_name"], "new_years_day")


if __name__ == "__main__":
    unittest.main()
