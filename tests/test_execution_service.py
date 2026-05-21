"""Tests for ExecutionService: order submission, reconciliation loop, and execution classification."""
import unittest

from config import TECH_UNIVERSE
from core.execution import ExecutionService


class MockBroker:
    def __init__(self, execution_report=None, account_summary=None):
        self._execution_report = execution_report or []
        self._account_summary = account_summary or (100000.0, {t: 0 for t in TECH_UNIVERSE})
        self.submit_calls = 0
        self.summary_calls = 0

    def submit_orders(self, orders: list) -> list:
        self.submit_calls += 1
        return self._execution_report

    def get_account_summary(self) -> tuple:
        self.summary_calls += 1
        return self._account_summary


def _zero_positions():
    return {t: 0 for t in TECH_UNIVERSE}


FILLED_REPORT = [
    {"ticker": "AAPL", "action": "BUY", "requested": 100, "filled": 100,
     "avg_fill_price": 100.0, "commission": 1.0, "elapsed_sec": 1.2,
     "status_detail": "filled_complete", "status": "Filled"},
]

PARTIAL_REPORT = [
    {"ticker": "AAPL", "action": "BUY", "requested": 100, "filled": 50,
     "avg_fill_price": 101.0, "commission": 0.5, "elapsed_sec": 3.0,
     "status_detail": "partial_open", "status": "Partial"},
]

CANCELLED_REPORT = [
    {"ticker": "AAPL", "action": "BUY", "requested": 100, "filled": 0,
     "avg_fill_price": 0.0, "commission": 0.0, "elapsed_sec": 10.2,
     "timeout_cancel_requested": True, "status_detail": "timeout_cancelled", "status": "Cancelled"},
]


class ExecutionServiceTests(unittest.TestCase):
    def test_execute_returns_full_result_on_filled(self):
        after_cash = 90000.0
        after_positions = {"AAPL": 100}
        after_positions.update({t: 0 for t in TECH_UNIVERSE if t != "AAPL"})
        broker = MockBroker(
            execution_report=FILLED_REPORT,
            account_summary=(after_cash, after_positions),
        )
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[{"ticker": "AAPL", "action": "BUY", "shares": 100, "amount": 10000.0}],
            before_cash=100000.0,
            before_positions=_zero_positions(),
            reconcile_delay_sec=0.01,
        )

        self.assertEqual(result["execution_summary"]["status"], "filled")
        self.assertTrue(result["reconcile_ok"])
        self.assertEqual(result["after_cash"], after_cash)
        self.assertEqual(result["after_positions"]["AAPL"], 100)
        self.assertGreater(result["submit_sec"], 0)
        self.assertGreater(result["reconcile_sec"], 0)
        self.assertEqual(len(result["execution_report"]), 1)
        self.assertIn("reconciliation", result)
        self.assertIn("execution_summary", result)
        self.assertEqual(broker.submit_calls, 1)

    def test_execute_classifies_partial(self):
        after_cash = 95000.0
        after_positions = {"AAPL": 50}
        after_positions.update({t: 0 for t in TECH_UNIVERSE if t != "AAPL"})
        broker = MockBroker(
            execution_report=PARTIAL_REPORT,
            account_summary=(after_cash, after_positions),
        )
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[{"ticker": "AAPL", "action": "BUY", "shares": 100, "amount": 10000.0}],
            before_cash=100000.0,
            before_positions=_zero_positions(),
        )

        self.assertEqual(result["execution_summary"]["status"], "partial")
        self.assertTrue(result["reconcile_ok"])
        self.assertEqual(result["after_positions"]["AAPL"], 50)

    def test_execute_classifies_cancelled(self):
        broker = MockBroker(
            execution_report=CANCELLED_REPORT,
            account_summary=(100000.0, _zero_positions()),
        )
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[{"ticker": "AAPL", "action": "BUY", "shares": 100, "amount": 10000.0}],
            before_cash=100000.0,
            before_positions=_zero_positions(),
        )

        self.assertEqual(result["execution_summary"]["status"], "cancelled")
        self.assertEqual(result["after_cash"], 100000.0)

    def test_execute_handles_empty_orders(self):
        broker = MockBroker(execution_report=[], account_summary=(100000.0, _zero_positions()))
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[],
            before_cash=100000.0,
            before_positions=_zero_positions(),
        )

        self.assertEqual(result["execution_summary"]["status"], "submitted_no_report")
        self.assertEqual(len(result["execution_report"]), 0)

    def test_execute_retries_reconciliation_on_mismatch(self):
        mismatched_positions = {"AAPL": 200}
        mismatched_positions.update({t: 0 for t in TECH_UNIVERSE if t != "AAPL"})
        broker = MockBroker(
            execution_report=FILLED_REPORT,
            account_summary=(90000.0, mismatched_positions),
        )
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[{"ticker": "AAPL", "action": "BUY", "shares": 100, "amount": 10000.0}],
            before_cash=100000.0,
            before_positions=_zero_positions(),
            max_reconcile_retries=3,
            reconcile_delay_sec=0.01,
        )

        self.assertFalse(result["reconcile_ok"])
        self.assertIn("AAPL", result["reconciliation"].get("mismatched", {}))
        self.assertGreater(broker.summary_calls, 1)

    def test_execute_mismatch_returns_latest_reconciliation(self):
        after_cash = 95000.0
        after_positions = {"AAPL": 60}
        after_positions.update({t: 0 for t in TECH_UNIVERSE if t != "AAPL"})
        broker = MockBroker(
            execution_report=PARTIAL_REPORT,
            account_summary=(after_cash, after_positions),
        )
        svc = ExecutionService(broker=broker)
        result = svc.execute(
            orders=[{"ticker": "AAPL", "action": "BUY", "shares": 100, "amount": 10000.0}],
            before_cash=100000.0,
            before_positions=_zero_positions(),
        )

        mismatched = result["reconciliation"].get("mismatched", {})
        if not result["reconcile_ok"]:
            self.assertIn("AAPL", mismatched)
            self.assertEqual(mismatched["AAPL"]["expected"], 50)
            self.assertEqual(mismatched["AAPL"]["actual"], 60)


if __name__ == "__main__":
    unittest.main()
