import unittest

from config import MAX_HOLDINGS, MAX_SINGLE_POSITION, MIN_POSITION_WEIGHT, TECH_UNIVERSE
from llm.validator import validate_and_clean_strategy_plan


class ValidatorCoreTests(unittest.TestCase):
    def test_returns_safe_minimal_plan_when_input_is_not_dict(self):
        cleaned, errors, warnings = validate_and_clean_strategy_plan("bad-plan")

        self.assertEqual(cleaned, {"reasoning": "invalid", "allocations": {}})
        self.assertEqual(errors, ["plan_not_dict"])
        self.assertEqual(warnings, [])

    def test_cleans_invalid_weights_and_metadata_fields(self):
        long_quote = "q" * 400
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": 123,
                "selected_strategies": [
                    "core_hold_momentum_tilt",
                    "unknown_strategy",
                ],
                "allocations": {
                    "AAPL": 0.35,
                    "MSFT": "oops",
                    "NVDA": -0.10,
                    "UNKNOWN": 0.50,
                },
                "evidence": [
                    "bad-evidence",
                    {"source": "news", "quote": long_quote, "ticker": "BAD", "chunk_id": 7, "url": "not-a-url", "timestamp": 12345},
                    {"source": "macro", "quote": "valid", "ticker": "AAPL", "chunk_id": "macro-1", "url": "https://example.com/doc/1", "timestamp": "2026-05-14T09:30:00Z"},
                ],
                "evidence_weights": {
                    "news": 3,
                    "market": "bad",
                    "macro": -1,
                    "sec_edgar": 1,
                    "other": 2,
                },
                "self_evaluation": {
                    "confidence": 68,
                    "key_risks": ["r" * 200, "市场回撤风险"],
                    "counterpoints": ["如果宏观转弱则应提高现金", ""],
                },
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["reasoning"], "123")
        self.assertEqual(cleaned["selected_strategies"], ["core_hold_momentum_tilt"])
        self.assertEqual(cleaned["allocations"]["AAPL"], MAX_SINGLE_POSITION)
        self.assertEqual(cleaned["allocations"]["MSFT"], 0.0)
        self.assertEqual(cleaned["allocations"]["NVDA"], 0.0)
        self.assertNotIn("UNKNOWN", cleaned["allocations"])
        self.assertEqual(len(cleaned["evidence"]), 2)
        self.assertEqual(cleaned["evidence"][0]["ticker"], None)
        self.assertEqual(len(cleaned["evidence"][0]["quote"]), 300)
        self.assertEqual(cleaned["evidence"][0]["chunk_id"], "7")
        self.assertEqual(cleaned["evidence"][0]["url"], None)
        self.assertEqual(cleaned["evidence"][0]["timestamp"], "12345")
        self.assertEqual(cleaned["evidence"][1]["ticker"], "AAPL")
        self.assertEqual(cleaned["evidence"][1]["chunk_id"], "macro-1")
        self.assertEqual(cleaned["evidence"][1]["url"], "https://example.com/doc/1")
        self.assertEqual(cleaned["evidence"][1]["timestamp"], "2026-05-14T09:30:00Z")
        self.assertAlmostEqual(cleaned["evidence_weights"]["news"], 0.75)
        self.assertAlmostEqual(cleaned["evidence_weights"]["sec_edgar"], 0.25)
        self.assertNotIn("market", cleaned["evidence_weights"])
        self.assertNotIn("macro", cleaned["evidence_weights"])
        self.assertAlmostEqual(cleaned["self_evaluation"]["confidence"], 0.68)
        self.assertEqual(len(cleaned["self_evaluation"]["key_risks"]), 2)
        self.assertEqual(len(cleaned["self_evaluation"]["key_risks"][0]), 160)
        self.assertEqual(cleaned["self_evaluation"]["counterpoints"], ["如果宏观转弱则应提高现金"])
        self.assertIn("reasoning_not_str", warnings)
        self.assertIn("unknown_strategy_id:unknown_strategy", warnings)
        self.assertIn("weight_over_single_limit_clipped:AAPL", warnings)
        self.assertIn("weight_not_number:MSFT", warnings)
        self.assertIn("weight_negative:NVDA", warnings)
        self.assertIn("evidence_weight_not_number:market", warnings)
        self.assertIn("evidence_weight_negative:macro", warnings)
        self.assertIn("unknown_evidence_weight_source:other", warnings)
        self.assertIn("self_evaluation_confidence_pct_normalized", warnings)

    def test_applies_min_weight_and_max_holdings_rules(self):
        allocations = {
            "AAPL": 0.10,
            "MSFT": 0.09,
            "NVDA": 0.08,
            "GOOGL": 0.07,
            "META": 0.06,
            "AMZN": 0.05,
            "TSLA": 0.04,
            "PLTR": MIN_POSITION_WEIGHT / 2,
        }
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "应用组合构建规则",
                "selected_strategies": [],
                "allocations": allocations,
                "evidence": [],
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["allocations"]["PLTR"], 0.0)
        non_zero = [ticker for ticker in TECH_UNIVERSE if cleaned["allocations"][ticker] > 0.0]
        self.assertEqual(len(non_zero), MAX_HOLDINGS)
        self.assertNotIn("TSLA", non_zero)
        self.assertIn("min_position_weight_applied", warnings)
        self.assertIn("max_holdings_applied", warnings)

    def test_ignores_non_dict_evidence_weights(self):
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "evidence weights bad",
                "selected_strategies": [],
                "allocations": {"AAPL": 0.1},
                "evidence": [],
                "evidence_weights": ["news", "market"],
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["evidence_weights"], {})
        self.assertIn("evidence_weights_not_dict", warnings)

    def test_ignores_invalid_self_evaluation_payload(self):
        cleaned, errors, warnings = validate_and_clean_strategy_plan(
            {
                "reasoning": "self evaluation bad",
                "selected_strategies": [],
                "allocations": {"AAPL": 0.1},
                "evidence": [],
                "self_evaluation": ["bad"],
            }
        )

        self.assertEqual(errors, [])
        self.assertEqual(cleaned["self_evaluation"]["confidence"], None)
        self.assertEqual(cleaned["self_evaluation"]["key_risks"], [])
        self.assertEqual(cleaned["self_evaluation"]["counterpoints"], [])
        self.assertIn("self_evaluation_not_dict", warnings)


if __name__ == "__main__":
    unittest.main()
