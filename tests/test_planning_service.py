"""Tests for PlanningService: RAG retrieval, LLM planning, and portfolio rebalancing in isolation."""
import unittest

from config import TECH_UNIVERSE
from core.planning import PlanningService


def _zero_positions():
    return {ticker: 0 for ticker in TECH_UNIVERSE}


class FakeLLM:
    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {
            "focus_sources": ["positions", "market", "sec_edgar"],
            "avoid_sources": [],
            "rationale": "测试路由",
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "增配 AAPL",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.20},
            "evidence_weights": {"news": 0.5, "market": 0.3},
            "self_evaluation": {"confidence": 0.74, "key_risks": ["动量回撤"], "counterpoints": []},
            "evidence": [{"source": "news", "quote": "风险偏好平稳。", "ticker": "AAPL"}],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


class FakeLLMInvalid:
    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {"focus_sources": [], "avoid_sources": [], "rationale": "", "_audit": {}}

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "无效策略",
            "selected_strategies": [],
            "allocations": {},
            "evidence": [],
            "_valid": False,
            "_errors": ["allocations_not_dict"],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


class FakeRetriever:
    def fetch_macro_data(self) -> str:
        return "- VIX: 18.0\n- 10Y: 4.10%"

    def fetch_fundamental_data(self) -> str:
        return "- AAPL: PE 25.0"

    def fetch_news(self) -> str:
        return "标题: 科技股情绪稳定\n摘要: 风险偏好平稳。"

    def fetch_market_data(self) -> dict:
        return {
            "context_string": "- AAPL: $100.00, +3.00%",
            "prices": {ticker: 100.0 for ticker in TECH_UNIVERSE},
        }

    def fetch_filing_data(self) -> dict:
        return {
            "context_string": "- AAPL: 8-K on 2026-05-14",
            "evidence": [{"source": "sec_edgar", "ticker": "AAPL", "quote": "8-K filed.", "chunk_id": "sec:AAPL:8-K:0", "url": "https://sec.gov/...", "timestamp": "2026-05-14T13:30:00Z"}],
            "source": "sec_edgar_recent_filings",
        }

    def get_provider_status(self) -> dict:
        return {
            "market": {"selected_provider": "fake", "mode": "fresh", "detail": "test"},
            "filing": {"selected_provider": "fake", "mode": "fresh", "detail": "test"},
        }


class FakeRetrieverNoPrices:
    def fetch_macro_data(self) -> str:
        return ""
    def fetch_fundamental_data(self) -> str:
        return ""
    def fetch_news(self) -> str:
        return ""
    def fetch_market_data(self) -> dict:
        return {"context_string": "", "prices": {}}
    def fetch_filing_data(self) -> dict:
        return {"context_string": "", "evidence": [], "source": ""}
    def get_provider_status(self) -> dict:
        return {}


class FakeLLMNoOrders:
    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {"focus_sources": [], "avoid_sources": [], "rationale": "", "_audit": {}}

    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "维持现状",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {},
            "evidence_weights": {},
            "self_evaluation": {"confidence": 0.5, "key_risks": [], "counterpoints": []},
            "evidence": [],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "test", "model_endpoint": "fake-llm"},
        }


class FakeMarketSession:
    def __init__(self, state="rth", can_place=True):
        self._state = state
        self._can_place = can_place

    def as_dict(self) -> dict:
        return {
            "market_state": self._state,
            "session_reason": "rth_open" if self._state == "rth" else "closed",
            "is_trading_day": True,
            "is_half_day": False,
            "effective_rth_end": "16:00",
            "can_place_orders": self._can_place,
            "label": self._state,
            "holiday_name": None,
            "early_close_name": None,
        }


class PlanningServiceTests(unittest.TestCase):
    def test_retrieve_context_returns_full_context_dict(self):
        svc = PlanningService(llm_client=FakeLLM(), retriever=FakeRetriever())
        session = FakeMarketSession(state="rth")
        ctx = svc.retrieve_context(
            cash=100000.0,
            positions=_zero_positions(),
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        self.assertIsNotNone(ctx)
        self.assertIn("rag_sec", ctx)
        self.assertGreater(ctx["rag_sec"], 0)
        self.assertEqual(ctx["macro_data"], "- VIX: 18.0\n- 10Y: 4.10%")
        self.assertEqual(ctx["portfolio_value"], 100000.0)
        self.assertIn("retrieval_route", ctx)
        self.assertIn("retrieval_route_context", ctx)
        self.assertIn("current_prices", ctx)
        self.assertEqual(ctx["current_prices"]["AAPL"], 100.0)
        self.assertIn("current_positions_str", ctx)
        self.assertIn("provider_status", ctx)

    def test_retrieve_context_returns_none_when_no_prices(self):
        svc = PlanningService(llm_client=FakeLLM(), retriever=FakeRetrieverNoPrices())
        session = FakeMarketSession(state="rth")
        ctx = svc.retrieve_context(
            cash=100000.0,
            positions=_zero_positions(),
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        self.assertIsNone(ctx)

    def test_generate_plan_returns_ready_with_orders(self):
        svc = PlanningService(llm_client=FakeLLM(), retriever=FakeRetriever())
        session = FakeMarketSession(state="rth")
        ctx = svc.retrieve_context(
            cash=100000.0,
            positions=_zero_positions(),
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        plan = svc.generate_plan(
            cash=100000.0,
            positions=_zero_positions(),
            ctx=ctx,
            date_str="2026-05-20",
            run_mode="test",
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["status"], "ready")
        self.assertIn("proposed_orders", plan)
        self.assertEqual(len(plan["proposed_orders"]), 1)
        self.assertEqual(plan["proposed_orders"][0]["ticker"], "AAPL")
        self.assertGreater(plan["turnover_ratio"], 0)
        self.assertGreater(plan["llm_sec"], 0)
        self.assertIn("llm_audit", plan)

    def test_generate_plan_returns_invalid_when_llm_fails(self):
        svc = PlanningService(llm_client=FakeLLMInvalid(), retriever=FakeRetriever())
        session = FakeMarketSession(state="rth")
        ctx = svc.retrieve_context(
            cash=100000.0,
            positions=_zero_positions(),
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        plan = svc.generate_plan(
            cash=100000.0,
            positions=_zero_positions(),
            ctx=ctx,
            date_str="2026-05-20",
            run_mode="test",
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["status"], "invalid")
        self.assertEqual(plan["orders"], [])
        self.assertIn("errors", plan)
        self.assertEqual(plan["errors"], ["allocations_not_dict"])

    def test_generate_plan_returns_no_trade_when_no_orders_needed(self):
        svc = PlanningService(llm_client=FakeLLMNoOrders(), retriever=FakeRetriever())
        session = FakeMarketSession(state="rth")
        ctx = svc.retrieve_context(
            cash=100000.0,
            positions=_zero_positions(),
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        plan = svc.generate_plan(
            cash=100000.0,
            positions=_zero_positions(),
            ctx=ctx,
            date_str="2026-05-20",
            run_mode="test",
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["status"], "no_trade")
        self.assertEqual(plan["orders"], [])

    def test_retrieve_context_computes_portfolio_value_from_positions(self):
        svc = PlanningService(llm_client=FakeLLM(), retriever=FakeRetriever())
        session = FakeMarketSession(state="rth")
        positions = {"AAPL": 50, "MSFT": 30}
        ctx = svc.retrieve_context(
            cash=50000.0,
            positions=positions,
            market_session=session.as_dict(),
            date_str="2026-05-20",
            run_mode="test",
        )
        expected_value = 50000.0 + 50 * 100.0 + 30 * 100.0
        self.assertAlmostEqual(ctx["portfolio_value"], expected_value)


if __name__ == "__main__":
    unittest.main()
