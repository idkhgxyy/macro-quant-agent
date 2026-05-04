import unittest

from llm.validator import validate_and_clean_strategy_plan


class ValidatorRiskExposureTests(unittest.TestCase):
    def test_applies_mega_cap_platform_group_cap(self):
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "控制平台股集中度。",
                "selected_strategies": [],
                "allocations": {
                    "AAPL": 0.20,
                    "MSFT": 0.20,
                    "GOOGL": 0.20,
                    "META": 0.20,
                    "AMZN": 0.15,
                },
                "evidence": [],
            }
        )

        self.assertEqual(errors, [])
        mega_sum = sum(cleaned["allocations"][t] for t in ["AAPL", "MSFT", "GOOGL", "META", "AMZN"])
        self.assertLessEqual(mega_sum, 0.55 + 1e-9)
        self.assertIn("risk_group_cap_applied:mega_cap_platform", warnings)

    def test_applies_high_beta_growth_group_cap(self):
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "压缩高波动成长股暴露。",
                "selected_strategies": [],
                "allocations": {
                    "TSLA": 0.18,
                    "PLTR": 0.12,
                    "AAPL": 0.10,
                },
                "evidence": [],
            }
        )

        self.assertEqual(errors, [])
        growth_sum = cleaned["allocations"]["TSLA"] + cleaned["allocations"]["PLTR"]
        self.assertLessEqual(growth_sum, 0.22 + 1e-9)
        self.assertIn("risk_group_cap_applied:high_beta_growth", warnings)


if __name__ == "__main__":
    unittest.main()
