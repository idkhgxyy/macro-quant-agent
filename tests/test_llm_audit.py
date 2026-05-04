import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from llm.volcengine import VolcengineLLMClient


def _fake_response(text: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text)
            )
        ]
    )


class LlmAuditTests(unittest.TestCase):
    def test_generate_strategy_attaches_audit(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(
            return_value=_fake_response(
                json.dumps(
                    {
                        "reasoning": "保持分散配置。",
                        "selected_strategies": [],
                        "allocations": {"AAPL": 0.2, "MSFT": 0.2},
                        "evidence": [],
                    },
                    ensure_ascii=False,
                )
            )
        )

        plan = client.generate_strategy("news", "market", "macro", "fundamental", "positions", mode="live")
        audit = plan.get("_audit")

        self.assertIsInstance(audit, dict)
        self.assertEqual(audit.get("model_endpoint"), "ep-test")
        self.assertEqual(audit.get("selected_attempt"), "initial")
        self.assertEqual(audit.get("attempt_count"), 1)
        self.assertIn("prompt_version", audit)
        self.assertIn("raw_response", audit)
        self.assertIsInstance(audit.get("validator_warnings"), list)

    def test_generate_strategy_records_repair_attempt(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(
            side_effect=[
                _fake_response(
                    json.dumps(
                        {
                            "reasoning": "先给一个坏格式。",
                            "selected_strategies": [],
                            "allocations": [],
                            "evidence": [],
                        },
                        ensure_ascii=False,
                    )
                ),
                _fake_response(
                    json.dumps(
                        {
                            "reasoning": "修正后输出。",
                            "selected_strategies": [],
                            "allocations": {"AAPL": 0.15, "MSFT": 0.15},
                            "evidence": [],
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )

        plan = client.generate_strategy("news", "market", "macro", "fundamental", "positions", mode="live")
        audit = plan.get("_audit")

        self.assertTrue(plan.get("_valid"))
        self.assertTrue(audit.get("repaired"))
        self.assertEqual(audit.get("selected_attempt"), "repair")
        self.assertEqual(audit.get("attempt_count"), 2)
        self.assertEqual(audit.get("initial_validator_errors"), ["allocations_not_dict"])
        self.assertIn("repair_raw_response", audit)
        self.assertEqual(audit.get("validator_errors"), [])


if __name__ == "__main__":
    unittest.main()
