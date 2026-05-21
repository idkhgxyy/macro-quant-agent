"""Integration test: MacroQuantAgent with all 4 services injected, end-to-end.
Runs the full daily routine via the new v2 path (_run_v2), producing
real artifacts that are verified and then cleaned up.
"""
import os
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import tempfile

from config import TECH_UNIVERSE
from core.agent import MacroQuantAgent
from core.planning import PlanningService
from core.execution import ExecutionService as ExecutionSvc
from core.persistence import PersistenceService
from core.ops import OpsService
from execution.broker import MockBroker


def _zero_positions():
    return {ticker: 0 for ticker in TECH_UNIVERSE}


class FakeRetriever:
    def fetch_macro_data(self) -> str:
        return "- VIX: 18.0\n- 10Y: 4.10%"
    def fetch_fundamental_data(self) -> str:
        return "- AAPL: PE 25.0"
    def fetch_news(self) -> str:
        return "标题: 科技股情绪稳定\n摘要: 风险偏好平稳。"
    def fetch_market_data(self) -> dict:
        return {"context_string": "- AAPL: $100.00, +3.00%", "prices": {t: 100.0 for t in TECH_UNIVERSE}}
    def fetch_filing_data(self) -> dict:
        return {"context_string": "- AAPL: 8-K", "evidence": [{"source": "sec_edgar", "ticker": "AAPL", "quote": "8-K", "chunk_id": "0", "url": "", "timestamp": ""}], "source": "sec_edgar"}
    def get_provider_status(self) -> dict:
        return {"market": {"selected_provider": "fake", "mode": "fresh", "detail": "e2e"}, "filing": {"selected_provider": "fake", "mode": "fresh", "detail": "e2e"}}


class FakeLLM:
    def generate_retrieval_route(self, **kwargs) -> dict:
        return {"focus_sources": ["positions", "market"], "avoid_sources": [], "rationale": "e2e", "_audit": {"prompt_version": "e2e", "model_endpoint": "fake"}}
    def generate_strategy(self, *args, **kwargs) -> dict:
        return {
            "reasoning": "增配 AAPL",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.20},
            "evidence_weights": {"news": 0.5, "market": 0.3},
            "self_evaluation": {"confidence": 0.74, "key_risks": ["动量回撤"], "counterpoints": []},
            "evidence": [{"source": "news", "quote": "风险偏好平稳。", "ticker": "AAPL"}],
            "_valid": True, "_errors": [], "_warnings": [],
            "_audit": {"prompt_version": "e2e", "model_endpoint": "fake"},
        }


def _open_market_session(*args, **kwargs):
    return {"market_state": "rth", "session_reason": "rth_open", "is_trading_day": True, "is_half_day": False, "effective_rth_end": "16:00", "can_place_orders": True, "holiday_name": None, "early_close_name": None}


@contextmanager
def _isolated():
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        rt = os.path.join(tmp, "runtime")
        with patch.dict(os.environ, {"RUNTIME_STATE_DIR": rt, "HEARTBEAT_STATE_PATH": os.path.join(rt, "heartbeat.json"), "KILL_SWITCH_STATE_PATH": os.path.join(rt, "kill_switch.json")}, clear=False):
            os.chdir(tmp)
            try:
                yield tmp
            finally:
                os.chdir(old)


class AgentV2E2ETests(unittest.TestCase):
    def test_v2_happy_path_produces_all_artifacts(self):
        with _isolated() as tmpdir:
            llm = FakeLLM()
            retriever = FakeRetriever()
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=llm,
                retriever=retriever,
                broker=broker,
                run_mode="test",
                planning_service=PlanningService(llm_client=llm, retriever=retriever),
                execution_service=ExecutionSvc(broker=broker),
                persistence_service=PersistenceService(),
                ops_service=OpsService(),
            )
            with patch("core.agent.get_market_session", side_effect=_open_market_session), \
                 patch("utils.alerting.evaluate_and_notify", return_value={"triggered": False, "reason": None, "items": []}):
                agent.run_daily_routine()

            self.assertTrue(os.path.exists(os.path.join(tmpdir, "snapshots")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "ledger")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "metrics")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "runtime", "heartbeat.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "portfolio_state.json")))
            snap_files = os.listdir(os.path.join(tmpdir, "snapshots"))
            self.assertTrue(any(f.startswith("rag_") for f in snap_files), f"no rag snapshot in {snap_files}")
            self.assertTrue(any(f.startswith("decision_") for f in snap_files), f"no decision snapshot in {snap_files}")
            ledger_files = os.listdir(os.path.join(tmpdir, "ledger"))
            self.assertTrue(any(f.startswith("execution_") for f in ledger_files), f"no ledger file in {ledger_files}")

    def test_v2_planning_only_skips_submission(self):
        with _isolated() as tmpdir:
            llm = FakeLLM()
            retriever = FakeRetriever()
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=llm,
                retriever=retriever,
                broker=broker,
                run_mode="test",
                planning_service=PlanningService(llm_client=llm, retriever=retriever),
                execution_service=ExecutionSvc(broker=broker),
                persistence_service=PersistenceService(),
                ops_service=OpsService(),
            )
            closed_session = {"market_state": "closed", "session_reason": "weekend", "is_trading_day": False, "is_half_day": False, "effective_rth_end": "16:00", "can_place_orders": False, "holiday_name": None, "early_close_name": None}
            with patch("core.agent.get_market_session", side_effect=[closed_session]), \
                 patch("utils.alerting.evaluate_and_notify", return_value={"triggered": False, "reason": None, "items": []}):
                agent.run_daily_routine()
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "ledger", "execution_2026-05-20.json")))
            snap_files = os.listdir(os.path.join(tmpdir, "snapshots"))
            decision_files = [f for f in snap_files if f.startswith("decision_")]
            self.assertTrue(len(decision_files) > 0, "expected at least one decision snapshot")

    def test_v2_kill_switch_blocks_execution(self):
        with _isolated() as tmpdir:
            llm = FakeLLM()
            retriever = FakeRetriever()
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=llm,
                retriever=retriever,
                broker=broker,
                run_mode="test",
                planning_service=PlanningService(llm_client=llm, retriever=retriever),
                execution_service=ExecutionSvc(broker=broker),
                persistence_service=PersistenceService(),
                ops_service=OpsService(),
            )
            OpsService.trigger_kill_switch(reason="pre_test_lock", source="test")
            with patch("core.agent.get_market_session", side_effect=_open_market_session), \
                 patch("utils.alerting.evaluate_and_notify", return_value={"triggered": False, "reason": None, "items": []}):
                agent.run_daily_routine()
            OpsService().check_kill_switch()
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "snapshots", "rag_2026-05-20.json")),
                             "v2 should skip RAG when kill switch is locked")


if __name__ == "__main__":
    unittest.main()
