"""Tests for Self-Improving Memory: record, reflect, load cycle and agent integration."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.memory import (
    record_experience,
    get_active_rules,
    get_rules_prompt_section,
    get_memory_stats,
    update_outcome,
    _memory_path,
)


class MemoryUnitTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env_patch = patch.dict(os.environ, {"RUNTIME_STATE_DIR": self._tmpdir})
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        # Clean up memory file
        path = _memory_path()
        if os.path.exists(path):
            os.remove(path)

    def test_record_experience_creates_memory_file(self):
        record_experience(
            date_str="2026-06-13",
            decision_summary="增配AAPL至20%",
            allocations={"AAPL": 0.20},
            orders=[{"ticker": "AAPL", "action": "buy", "shares": 10}],
            market_context="VIX 18.0, 10Y 4.1%",
        )
        path = _memory_path()
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(len(data["experiences"]), 1)
        self.assertEqual(data["experiences"][0]["date"], "2026-06-13")
        self.assertEqual(data["experiences"][0]["allocations"], {"AAPL": 0.20})

    def test_record_experience_truncates_long_text(self):
        long_text = "x" * 1000
        record_experience(
            date_str="2026-06-13",
            decision_summary=long_text,
            allocations={},
            orders=[],
            market_context=long_text,
        )
        with open(_memory_path()) as f:
            data = json.load(f)
        exp = data["experiences"][0]
        self.assertLessEqual(len(exp["decision_summary"]), 500)
        self.assertLessEqual(len(exp["market_context"]), 300)

    def test_record_experience_keeps_last_30(self):
        for i in range(35):
            record_experience(
                date_str=f"2026-06-{i+1:02d}",
                decision_summary=f"Day {i}",
                allocations={},
                orders=[],
                market_context="",
            )
        with open(_memory_path()) as f:
            data = json.load(f)
        self.assertEqual(len(data["experiences"]), 30)

    def test_get_active_rules_filters_by_confidence(self):
        # Write rules directly
        path = _memory_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "experiences": [],
                "rules": [
                    {"id": "R1", "rule": "High conf rule", "confidence": 0.8},
                    {"id": "R2", "rule": "Low conf rule", "confidence": 0.2},
                    {"id": "R3", "rule": "Medium conf rule", "confidence": 0.5},
                ],
                "last_reflection": None,
            }, f)
        rules = get_active_rules()
        self.assertEqual(len(rules), 2)
        rule_ids = [r["id"] for r in rules]
        self.assertIn("R1", rule_ids)
        self.assertIn("R3", rule_ids)
        self.assertNotIn("R2", rule_ids)

    def test_get_rules_prompt_section_empty_when_no_rules(self):
        section = get_rules_prompt_section()
        self.assertEqual(section, "")

    def test_get_rules_prompt_section_with_rules(self):
        path = _memory_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "experiences": [],
                "rules": [
                    {"id": "R1", "rule": "VIX>25时降低高beta", "confidence": 0.8},
                ],
                "last_reflection": None,
            }, f)
        section = get_rules_prompt_section()
        self.assertIn("R1", section)
        self.assertIn("VIX>25", section)
        self.assertIn("🟢", section)

    def test_update_outcome(self):
        record_experience(
            date_str="2026-06-13",
            decision_summary="test",
            allocations={},
            orders=[],
            market_context="",
        )
        update_outcome("2026-06-13", "盈利2%")
        with open(_memory_path()) as f:
            data = json.load(f)
        self.assertEqual(data["experiences"][0]["outcome"], "盈利2%")

    def test_get_memory_stats(self):
        record_experience(
            date_str="2026-06-13",
            decision_summary="test",
            allocations={},
            orders=[],
            market_context="",
        )
        stats = get_memory_stats()
        self.assertEqual(stats["experience_count"], 1)
        self.assertEqual(stats["rule_count"], 0)
        self.assertEqual(stats["latest_experience"], "2026-06-13")


class MemoryAgentIntegrationTests(unittest.TestCase):
    """Test that agent._finalize_run calls record_experience on successful runs."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env_patch = patch.dict(
            os.environ,
            {
                "RUNTIME_STATE_DIR": self._tmpdir,
                "HEARTBEAT_STATE_PATH": os.path.join(self._tmpdir, "heartbeat.json"),
                "KILL_SWITCH_STATE_PATH": os.path.join(self._tmpdir, "kill_switch.json"),
            },
        )
        self._env_patch.start()

    def tearDown(self):
        self._env_patch.stop()
        path = _memory_path()
        if os.path.exists(path):
            os.remove(path)

    def test_agent_records_experience_on_successful_trade(self):
        from core.agent import MacroQuantAgent
        from core.planning import PlanningService
        from core.execution import ExecutionService as ExecutionSvc
        from core.persistence import PersistenceService
        from core.ops import OpsService
        from execution.broker import MockBroker
        from config import TECH_UNIVERSE

        # Import test helpers
        from tests.test_agent_integration import (
            FakeLLMValid,
            FakeRetriever,
            _open_market_session,
        )

        old_cwd = os.getcwd()
        os.chdir(self._tmpdir)
        try:
            broker = MockBroker(initial_cash=100000.0)
            llm = FakeLLMValid()
            retriever = FakeRetriever()
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

            with patch("core.agent.get_market_session", side_effect=_open_market_session), patch(
                "utils.alerting.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ), patch("random.random", return_value=0.5):
                agent.run_daily_routine()

            # Verify memory file was created
            path = _memory_path()
            self.assertTrue(os.path.exists(path), "Memory file should be created after a successful run")
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(len(data["experiences"]), 1)
            self.assertIn("增配", data["experiences"][0]["decision_summary"])
            self.assertEqual(data["experiences"][0]["allocations"], {"AAPL": 0.20})
        finally:
            os.chdir(old_cwd)

    def test_agent_does_not_record_on_market_closed(self):
        from core.agent import MacroQuantAgent
        from core.planning import PlanningService
        from core.execution import ExecutionService as ExecutionSvc
        from core.persistence import PersistenceService
        from core.ops import OpsService
        from execution.broker import MockBroker

        from tests.test_agent_integration import FakeLLMValid, FakeRetriever

        def _closed_market(*_args, **_kwargs):
            return {
                "market_state": "closed",
                "session_reason": "weekend",
                "is_trading_day": False,
                "is_half_day": False,
                "effective_rth_end": None,
                "can_place_orders": False,
                "holiday_name": None,
                "early_close_name": None,
            }

        old_cwd = os.getcwd()
        os.chdir(self._tmpdir)
        try:
            broker = MockBroker(initial_cash=100000.0)
            llm = FakeLLMValid()
            retriever = FakeRetriever()
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

            with patch("core.agent.get_market_session", side_effect=_closed_market), patch(
                "utils.alerting.evaluate_and_notify",
                return_value={"triggered": False, "items": []},
            ):
                agent.run_daily_routine()

            # Verify memory file was NOT created
            path = _memory_path()
            self.assertFalse(os.path.exists(path), "Memory file should NOT be created on market_closed")
        finally:
            os.chdir(old_cwd)
