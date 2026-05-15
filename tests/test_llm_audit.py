import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from llm.volcengine import (
    VolcengineLLMClient,
    build_review_summary_fallback,
    build_retrieval_route_fallback,
)


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

    def test_generate_review_summary_attaches_audit(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(
            return_value=_fake_response(
                json.dumps(
                    {
                        "summary": "本次策略完成执行闭环。",
                        "key_points": ["AAPL 是核心增配方向。", "成交率整体稳定。"],
                        "risks": ["MSFT 成交略慢。"],
                        "next_steps": ["继续跟踪后续收益兑现。"],
                    },
                    ensure_ascii=False,
                )
            )
        )

        summary = client.generate_review_summary({"status": "filled", "highlights": ["AAPL 增配。"]}, mode="report")
        audit = summary.get("_audit")

        self.assertEqual(summary.get("summary"), "本次策略完成执行闭环。")
        self.assertEqual(summary.get("key_points"), ["AAPL 是核心增配方向。", "成交率整体稳定。"])
        self.assertEqual(summary.get("risks"), ["MSFT 成交略慢。"])
        self.assertEqual(summary.get("next_steps"), ["继续跟踪后续收益兑现。"])
        self.assertIsInstance(audit, dict)
        self.assertEqual(audit.get("model_endpoint"), "ep-test")
        self.assertEqual(audit.get("selected_attempt"), "initial")
        self.assertEqual(audit.get("attempt_count"), 1)

    def test_generate_review_summary_falls_back_when_response_is_invalid(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(return_value=_fake_response("not-json"))

        summary = client.generate_review_summary(
            {
                "status": "partial",
                "highlights": ["执行成交率约 50%。"],
                "execution_quality": {"problem_order_count": 1, "fill_ratio": 0.5},
            },
            mode="report",
        )

        self.assertIn("部分执行", summary.get("summary", ""))
        self.assertTrue(summary.get("key_points"))
        self.assertTrue(summary.get("risks"))
        self.assertTrue(summary.get("next_steps"))
        self.assertEqual(summary.get("_audit", {}).get("selected_attempt"), "fallback_error")

    def test_build_review_summary_fallback_for_planning_only(self):
        summary = build_review_summary_fallback(
            {
                "status": "planning_only",
                "highlights": ["本次仅生成计划，未实际下单，原因：live_trading_disabled。"],
                "top_allocations": [{"ticker": "AAPL", "weight": 0.2}],
            },
            reason="no_config",
        )

        self.assertIn("仅生成投资计划", summary.get("summary", ""))
        self.assertTrue(summary.get("key_points"))
        self.assertTrue(summary.get("next_steps"))
        self.assertEqual(summary.get("_audit", {}).get("selected_attempt"), "fallback")
        self.assertEqual(summary.get("_audit", {}).get("call_error"), "no_config")

    def test_generate_retrieval_route_attaches_audit(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(
            return_value=_fake_response(
                json.dumps(
                    {
                        "focus_sources": ["positions", "market", "sec_edgar"],
                        "avoid_sources": ["macro"],
                        "rationale": "当前持仓与市场动量更直接影响本轮决策，官方公告可补充确认。",
                    },
                    ensure_ascii=False,
                )
            )
        )

        route = client.generate_retrieval_route(
            news_context="news",
            market_context="market",
            macro_context="macro",
            fundamental_context="fundamental",
            current_positions_summary="positions",
            filing_context="filings",
            provider_status={"market": {"mode": "fresh"}},
            mode="route",
        )
        audit = route.get("_audit")

        self.assertEqual(route.get("focus_sources"), ["positions", "market", "sec_edgar"])
        self.assertEqual(route.get("avoid_sources"), ["macro"])
        self.assertIn("当前持仓", route.get("rationale", ""))
        self.assertIsInstance(audit, dict)
        self.assertEqual(audit.get("selected_attempt"), "initial")
        self.assertEqual(audit.get("attempt_count"), 1)

    def test_generate_retrieval_route_falls_back_when_response_is_invalid(self):
        client = VolcengineLLMClient("dummy-key", "ep-test")
        client.client.chat.completions.create = MagicMock(return_value=_fake_response("bad-json"))

        route = client.generate_retrieval_route(
            news_context="标题: 科技股情绪稳定",
            market_context="- AAPL: 当前价格 $100.00",
            macro_context="- VIX 18",
            fundamental_context="- AAPL: PE 25",
            current_positions_summary="现金: $100,000.00 (100.0%)",
            filing_context="SEC EDGAR 公告证据暂不可用。",
            provider_status={"sec_edgar": {"mode": "degraded", "selected_provider": "none"}},
            mode="route",
        )

        self.assertIn("positions", route.get("focus_sources", []))
        self.assertIn("market", route.get("focus_sources", []))
        self.assertIn("sec_edgar", route.get("avoid_sources", []))
        self.assertEqual(route.get("_audit", {}).get("selected_attempt"), "fallback_error")

    def test_build_retrieval_route_fallback_marks_degraded_source_as_avoid(self):
        route = build_retrieval_route_fallback(
            news_context="标题: 科技股情绪稳定",
            market_context="- AAPL: 当前价格 $100.00",
            macro_context="- VIX 18",
            fundamental_context="- AAPL: PE 25",
            current_positions_summary="现金: $100,000.00 (100.0%)",
            filing_context="SEC EDGAR 公告证据暂不可用。",
            provider_status={"sec_edgar": {"mode": "degraded", "selected_provider": "none"}},
            reason="no_config",
        )

        self.assertIn("positions", route.get("focus_sources", []))
        self.assertIn("market", route.get("focus_sources", []))
        self.assertIn("sec_edgar", route.get("avoid_sources", []))
        self.assertEqual(route.get("_audit", {}).get("selected_attempt"), "fallback")


if __name__ == "__main__":
    unittest.main()
