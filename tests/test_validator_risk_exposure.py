"""Tests for validator risk-exposure group caps: sector concentration and custom group limits."""
import unittest

from config.risk import RISK_EXPOSURE_GROUP_CAPS
from llm.validator import validate_and_clean_strategy_plan


class ValidatorRiskExposureTests(unittest.TestCase):
    def test_applies_technology_sector_cap(self):
        """Technology sector tickers should be capped at their group max_sum."""
        tech_tickers = RISK_EXPOSURE_GROUP_CAPS.get("technology", {}).get("tickers", [])
        tech_cap = RISK_EXPOSURE_GROUP_CAPS.get("technology", {}).get("max_sum", 1.0)
        if not tech_tickers:
            self.skipTest("No technology sector group in current config")

        # Over-allocate to technology tickers to trigger the cap
        alloc = {t: 0.20 for t in tech_tickers}
        alloc["AMZN"] = 0.05  # non-tech to fill

        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "测试科技板块集中度限制。",
                "selected_strategies": [],
                "allocations": alloc,
                "evidence": [],
            }
        )

        self.assertEqual(errors, [])
        tech_sum = sum(cleaned["allocations"].get(t, 0) for t in tech_tickers)
        self.assertLessEqual(tech_sum, tech_cap + 1e-9)
        self.assertIn("risk_group_cap_applied:technology", warnings)

    def test_applies_consumer_cyclical_sector_cap(self):
        """Consumer Cyclical tickers should be capped at their group max_sum."""
        cc_tickers = RISK_EXPOSURE_GROUP_CAPS.get("consumer_cyclical", {}).get("tickers", [])
        cc_cap = RISK_EXPOSURE_GROUP_CAPS.get("consumer_cyclical", {}).get("max_sum", 1.0)
        if not cc_tickers:
            self.skipTest("No consumer_cyclical sector group in current config")

        # Over-allocate to consumer cyclical tickers
        alloc = {t: 0.25 for t in cc_tickers}
        alloc["AAPL"] = 0.05  # fill

        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "测试消费周期板块集中度限制。",
                "selected_strategies": [],
                "allocations": alloc,
                "evidence": [],
            }
        )

        self.assertEqual(errors, [])
        cc_sum = sum(cleaned["allocations"].get(t, 0) for t in cc_tickers)
        self.assertLessEqual(cc_sum, cc_cap + 1e-9)
        self.assertIn("risk_group_cap_applied:consumer_cyclical", warnings)

    def test_no_cap_when_within_limits(self):
        """Allocations within sector caps should pass without warnings."""
        alloc = {"AAPL": 0.10, "MSFT": 0.10, "GOOGL": 0.10, "AMZN": 0.10, "TSLA": 0.10}
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "合理分散配置。",
                "selected_strategies": [],
                "allocations": alloc,
                "evidence": [],
            }
        )
        self.assertEqual(errors, [])
        # No risk_group_cap_applied warnings
        cap_warnings = [w for w in warnings if "risk_group_cap_applied" in w]
        self.assertEqual(len(cap_warnings), 0)


if __name__ == "__main__":
    unittest.main()
