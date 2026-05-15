import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from config import TECH_UNIVERSE
from core.agent import MacroQuantAgent
from execution.broker import MockBroker


def _zero_positions():
    return {ticker: 0 for ticker in TECH_UNIVERSE}


class FakeRetriever:
    def fetch_macro_data(self) -> str:
        return "- VIX 恐慌指数: 18.0\n- 10年期美债收益率: 4.10%"

    def fetch_fundamental_data(self) -> str:
        return "- AAPL: 当前市盈率(PE) 25.0"

    def fetch_news(self) -> str:
        return "标题: 科技股情绪稳定\n摘要: 风险偏好平稳。"

    def fetch_market_data(self) -> dict:
        return {
            "context_string": "- AAPL: 当前价格 $100.00, 近一月涨跌幅 +3.00%",
            "prices": {ticker: 100.0 for ticker in TECH_UNIVERSE},
        }

    def fetch_filing_data(self) -> dict:
        return {
            "context_string": "- AAPL: 8-K on 2026-05-14 (Apple Inc.)",
            "evidence": [
                {
                    "source": "sec_edgar",
                    "ticker": "AAPL",
                    "quote": "8-K filed on 2026-05-14 for AAPL (Apple Inc.).",
                    "chunk_id": "sec:AAPL:8-K:2026-05-14:0",
                    "url": "https://www.sec.gov/Archives/example/aapl-8k.htm",
                    "timestamp": "2026-05-14T13:30:00Z",
                }
            ],
            "source": "sec_edgar_recent_filings",
        }

    def get_provider_status(self) -> dict:
        return {
            "market": {
                "selected_provider": "fake",
                "mode": "fresh",
                "detail": "integration_test",
                "attempts": [{"provider": "fake", "outcome": "success"}],
                "providers": [{"provider": "fake", "last_success_detail": "integration_test"}],
            },
            "filing": {
                "selected_provider": "fake",
                "mode": "fresh",
                "detail": "integration_test",
                "attempts": [{"provider": "fake", "outcome": "success"}],
                "providers": [{"provider": "fake", "last_success_detail": "integration_test"}],
            },
        }


class _FakeRouteMixin:
    def generate_retrieval_route(self, **_kwargs) -> dict:
        return {
            "focus_sources": ["positions", "market", "sec_edgar"],
            "avoid_sources": [],
            "rationale": "当前持仓约束与市场/公告信号更值得优先参考。",
            "_audit": {"prompt_version": "integration-test:route", "model_endpoint": "fake-llm"},
        }


class FakeLLMValid(_FakeRouteMixin):
    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "增配 AAPL，保持其余标的空仓。",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.20},
            "evidence_weights": {"news": 0.5, "market": 0.3, "sec_edgar": 0.2},
            "self_evaluation": {
                "confidence": 0.74,
                "key_risks": ["短期动量回撤风险"],
                "counterpoints": ["若宏观转弱，应提高现金"],
            },
            "evidence": [{"source": "news", "quote": "风险偏好平稳。", "ticker": "AAPL"}],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "integration-test", "model_endpoint": "fake-llm"},
        }


class FakeLLMInvalid(_FakeRouteMixin):
    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "输出未通过校验。",
            "selected_strategies": [],
            "allocations": {},
            "evidence": [],
            "_valid": False,
            "_errors": ["allocations_not_dict"],
            "_warnings": [],
            "_audit": {"prompt_version": "integration-test", "model_endpoint": "fake-llm"},
        }


class FakeLLMValidDual(_FakeRouteMixin):
    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "增配 AAPL 和 MSFT。",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {"AAPL": 0.10, "MSFT": 0.10},
            "evidence_weights": {"news": 0.4, "market": 0.4, "sec_edgar": 0.2},
            "self_evaluation": {
                "confidence": 0.66,
                "key_risks": ["执行偏差风险"],
                "counterpoints": ["若成交率继续偏低，应降低调仓幅度"],
            },
            "evidence": [{"source": "news", "quote": "风险偏好平稳。", "ticker": "AAPL"}],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "integration-test", "model_endpoint": "fake-llm"},
        }


class FakeLLMRisky(_FakeRouteMixin):
    def generate_strategy(self, *_args, **_kwargs) -> dict:
        return {
            "reasoning": "高集中高换手激进方案。",
            "selected_strategies": ["core_hold_momentum_tilt"],
            "allocations": {
                "AAPL": 0.80,
                "MSFT": 0.20,
                "NVDA": 0.20,
                "GOOGL": 0.20,
                "META": 0.20,
            },
            "evidence_weights": {"market": 0.5, "news": 0.3, "fundamental": 0.2},
            "self_evaluation": {
                "confidence": 0.82,
                "key_risks": ["组合过度集中风险"],
                "counterpoints": ["若无强证据，不应过度提升单票权重"],
            },
            "evidence": [{"source": "news", "quote": "风险偏好偏高。", "ticker": "AAPL"}],
            "_valid": True,
            "_errors": [],
            "_warnings": [],
            "_audit": {"prompt_version": "integration-test", "model_endpoint": "fake-llm"},
        }


class ScriptedBroker:
    def __init__(self, execution_report, *, initial_cash=100000.0, after_cash=None, initial_positions=None, after_positions=None):
        self.initial_cash = float(initial_cash)
        self.after_cash = float(self.initial_cash if after_cash is None else after_cash)
        self.initial_positions = dict(initial_positions or _zero_positions())
        self.after_positions = dict(after_positions or self.initial_positions)
        self.execution_report = list(execution_report)
        self.submitted = False

    def get_account_summary(self):
        if self.submitted:
            return self.after_cash, dict(self.after_positions)
        return self.initial_cash, dict(self.initial_positions)

    def submit_orders(self, _orders):
        self.submitted = True
        return list(self.execution_report)


@contextmanager
def isolated_runtime():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_dir = os.path.join(tmpdir, "runtime")
        with patch.dict(
            os.environ,
            {
                "RUNTIME_STATE_DIR": runtime_dir,
                "HEARTBEAT_STATE_PATH": os.path.join(runtime_dir, "heartbeat.json"),
                "KILL_SWITCH_STATE_PATH": os.path.join(runtime_dir, "kill_switch.json"),
            },
            clear=False,
        ):
            os.chdir(tmpdir)
            try:
                yield tmpdir
            finally:
                os.chdir(old_cwd)


def _open_market_session(*_args, **_kwargs):
    return {
        "market_state": "rth",
        "session_reason": "rth_open",
        "is_trading_day": True,
        "is_half_day": False,
        "effective_rth_end": "16:00",
        "can_place_orders": True,
        "holiday_name": None,
        "early_close_name": None,
    }


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_jsonl(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f.read().splitlines() if line.strip()]


def _latest_date(tmpdir: str) -> str:
    return next(name[len("decision_") : -5] for name in os.listdir(os.path.join(tmpdir, "snapshots")) if name.startswith("decision_"))


class AgentIntegrationTests(unittest.TestCase):
    def test_run_daily_routine_happy_path_persists_full_execution_artifacts(self):
        with isolated_runtime() as tmpdir:
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=FakeLLMValid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ), patch("random.random", return_value=0.5):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            rag_doc = _read_json(os.path.join(tmpdir, "snapshots", f"rag_{date_str}.json"))
            ledger_doc = _read_json(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "filled")
            self.assertEqual(decision_doc["payload"]["execution_summary"]["status"], "filled")
            self.assertEqual(decision_doc["payload"]["plan"]["evidence_weights"]["news"], 0.5)
            self.assertAlmostEqual(decision_doc["payload"]["plan"]["self_evaluation"]["confidence"], 0.74)
            self.assertEqual(decision_doc["payload"]["retrieval_route"]["focus_sources"][0], "positions")
            self.assertEqual(decision_doc["payload"]["positions_after"]["AAPL"], 200)
            self.assertEqual(decision_doc["payload"]["cash_after"], 80000.0)
            self.assertEqual(rag_doc["payload"]["provider_status"]["market"]["selected_provider"], "fake")
            self.assertEqual(rag_doc["payload"]["retrieval_route"]["focus_sources"][1], "market")
            self.assertTrue(ledger_doc["payload"]["reconciliation"]["ok"])
            self.assertEqual(ledger_doc["payload"]["after"]["positions"]["AAPL"], 200)
            self.assertEqual(heartbeat_doc["last_run"]["status"], "filled")
            self.assertEqual(heartbeat_doc["last_success"]["status"], "filled")
            self.assertEqual(metrics_items[-1]["status"], "filled")
            self.assertEqual(metrics_items[-1]["order_count"], 1)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "kill_switch.lock")))

    def test_run_daily_routine_invalid_llm_skips_execution_but_keeps_audit_trail(self):
        with isolated_runtime() as tmpdir:
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=FakeLLMInvalid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "invalid")
            self.assertEqual(decision_doc["payload"]["orders"], [])
            self.assertEqual(decision_doc["payload"]["llm_audit"]["prompt_version"], "integration-test")
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json")))
            self.assertEqual(heartbeat_doc["last_run"]["status"], "invalid")
            self.assertEqual(metrics_items[-1]["status"], "invalid")
            self.assertEqual(broker.server_cash, 100000.0)
            self.assertEqual(broker.server_positions["AAPL"], 0)

    def test_run_daily_routine_planning_only_keeps_orders_but_skips_submission(self):
        with isolated_runtime() as tmpdir:
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=FakeLLMValid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ), patch("core.agent.BROKER_TYPE", "ibkr"), patch("core.agent.ENABLE_LIVE_TRADING", False):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "planning_only")
            self.assertEqual(decision_doc["payload"]["planning_only_reason"], "live_trading_disabled")
            self.assertEqual(len(decision_doc["payload"]["orders"]), 1)
            self.assertEqual(len(decision_doc["payload"]["would_submit_preview"]), 1)
            self.assertEqual(decision_doc["payload"]["would_submit_preview"][0]["ticker"], "AAPL")
            self.assertFalse(decision_doc["payload"]["would_submit_preview"][0]["outside_rth"])
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json")))
            self.assertEqual(heartbeat_doc["last_run"]["status"], "planning_only")
            self.assertEqual(metrics_items[-1]["status"], "planning_only")
            self.assertEqual(broker.server_cash, 100000.0)
            self.assertEqual(broker.server_positions["AAPL"], 0)

    def test_run_daily_routine_planning_only_applies_portfolio_risk_controls(self):
        with isolated_runtime() as tmpdir:
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=FakeLLMRisky(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ), patch("core.agent.BROKER_TYPE", "ibkr"), patch("core.agent.ENABLE_LIVE_TRADING", False):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))
            orders = decision_doc["payload"]["orders"]
            amount_by_ticker = {row["ticker"]: float(row["amount"]) for row in orders}
            shares_by_ticker = {row["ticker"]: int(row["shares"]) for row in orders}
            total_amount = sum(float(row["amount"]) for row in orders)

            self.assertEqual(decision_doc["payload"]["status"], "planning_only")
            self.assertEqual(len(orders), 5)
            self.assertEqual(shares_by_ticker["AAPL"], shares_by_ticker["MSFT"])
            self.assertLessEqual(total_amount, 30000.0)
            self.assertEqual(total_amount, 30000.0)
            self.assertEqual(amount_by_ticker["AAPL"], 6000.0)
            self.assertEqual(decision_doc["payload"]["planning_only_reason"], "live_trading_disabled")
            self.assertEqual(metrics_items[-1]["status"], "planning_only")
            self.assertLessEqual(float(metrics_items[-1]["turnover"]), 0.30)

    def test_run_daily_routine_partial_problem_state_persists_execution_artifacts(self):
        with isolated_runtime() as tmpdir:
            broker = MockBroker(initial_cash=100000.0)
            agent = MacroQuantAgent(
                llm_client=FakeLLMValidDual(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ), patch("random.random", side_effect=[0.05, 0.5]):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            ledger_doc = _read_json(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "partial")
            self.assertEqual(decision_doc["payload"]["execution_summary"]["status"], "partial")
            self.assertTrue(ledger_doc["payload"]["reconciliation"]["ok"])
            self.assertEqual(len(ledger_doc["payload"]["execution_report"]), 2)
            self.assertEqual(ledger_doc["payload"]["execution_report"][0]["status"], "Rejected")
            self.assertEqual(ledger_doc["payload"]["execution_report"][1]["status"], "Filled")
            self.assertEqual(heartbeat_doc["last_run"]["status"], "partial")
            self.assertEqual(metrics_items[-1]["status"], "partial")
            self.assertEqual(broker.server_positions["MSFT"], 100)
            self.assertEqual(broker.server_positions["AAPL"], 0)

    def test_run_daily_routine_submitted_no_report_persists_empty_execution_report(self):
        with isolated_runtime() as tmpdir:
            broker = ScriptedBroker(
                execution_report=[],
                initial_cash=100000.0,
                after_cash=100000.0,
                initial_positions=_zero_positions(),
                after_positions=_zero_positions(),
            )
            agent = MacroQuantAgent(
                llm_client=FakeLLMValid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            ledger_doc = _read_json(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "submitted_no_report")
            self.assertEqual(decision_doc["payload"]["execution_summary"]["status"], "submitted_no_report")
            self.assertEqual(ledger_doc["payload"]["execution_report"], [])
            self.assertTrue(ledger_doc["payload"]["reconciliation"]["ok"])
            self.assertEqual(heartbeat_doc["last_run"]["status"], "submitted_no_report")
            self.assertEqual(metrics_items[-1]["status"], "submitted_no_report")

    def test_run_daily_routine_cancelled_problem_state_persists_execution_artifacts(self):
        with isolated_runtime() as tmpdir:
            broker = ScriptedBroker(
                execution_report=[
                    {
                        "ticker": "AAPL",
                        "action": "BUY",
                        "requested": 200,
                        "filled": 0,
                        "avg_fill_price": 0.0,
                        "commission": 0.0,
                        "status": "Cancelled",
                        "status_detail": "timeout_cancelled",
                        "submitted_at": "2026-05-14T00:00:00Z",
                        "completed_at": "2026-05-14T00:00:10Z",
                        "elapsed_sec": 10.0,
                        "timeout_cancel_requested": True,
                        "status_history": [{"status": "Cancelled", "ts": "2026-05-14T00:00:10Z"}],
                        "order_id": None,
                    }
                ],
                initial_cash=100000.0,
                after_cash=100000.0,
                initial_positions=_zero_positions(),
                after_positions=_zero_positions(),
            )
            agent = MacroQuantAgent(
                llm_client=FakeLLMValid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            ledger_doc = _read_json(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "cancelled")
            self.assertEqual(decision_doc["payload"]["execution_summary"]["status"], "cancelled")
            self.assertEqual(ledger_doc["payload"]["execution_report"][0]["status"], "Cancelled")
            self.assertTrue(ledger_doc["payload"]["reconciliation"]["ok"])
            self.assertEqual(heartbeat_doc["last_run"]["status"], "cancelled")
            self.assertEqual(metrics_items[-1]["status"], "cancelled")

    def test_run_daily_routine_unfilled_problem_state_persists_execution_artifacts(self):
        with isolated_runtime() as tmpdir:
            broker = ScriptedBroker(
                execution_report=[
                    {
                        "ticker": "AAPL",
                        "action": "BUY",
                        "requested": 200,
                        "filled": 0,
                        "avg_fill_price": 0.0,
                        "commission": 0.0,
                        "status": "Submitted",
                        "status_detail": "submitted_no_fill",
                        "submitted_at": "2026-05-14T00:00:00Z",
                        "completed_at": "2026-05-14T00:00:10Z",
                        "elapsed_sec": 10.0,
                        "timeout_cancel_requested": False,
                        "status_history": [{"status": "Submitted", "ts": "2026-05-14T00:00:10Z"}],
                        "order_id": None,
                    }
                ],
                initial_cash=100000.0,
                after_cash=100000.0,
                initial_positions=_zero_positions(),
                after_positions=_zero_positions(),
            )
            agent = MacroQuantAgent(
                llm_client=FakeLLMValid(),
                retriever=FakeRetriever(),
                broker=broker,
                run_mode="test",
            )

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "core.agent.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ):
                agent.run_daily_routine()

            date_str = _latest_date(tmpdir)
            decision_doc = _read_json(os.path.join(tmpdir, "snapshots", f"decision_{date_str}.json"))
            ledger_doc = _read_json(os.path.join(tmpdir, "ledger", f"execution_{date_str}.json"))
            heartbeat_doc = _read_json(os.path.join(tmpdir, "runtime", "heartbeat.json"))
            metrics_items = _read_jsonl(os.path.join(tmpdir, "metrics", "metrics.jsonl"))

            self.assertEqual(decision_doc["payload"]["status"], "unfilled")
            self.assertEqual(decision_doc["payload"]["execution_summary"]["status"], "unfilled")
            self.assertEqual(ledger_doc["payload"]["execution_report"][0]["status"], "Submitted")
            self.assertTrue(ledger_doc["payload"]["reconciliation"]["ok"])
            self.assertEqual(heartbeat_doc["last_run"]["status"], "unfilled")
            self.assertEqual(metrics_items[-1]["status"], "unfilled")


if __name__ == "__main__":
    unittest.main()
