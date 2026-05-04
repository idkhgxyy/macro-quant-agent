import unittest

from execution.reconcile import reconcile_execution


class ReconcileExecutionTests(unittest.TestCase):
    def test_reconcile_ok_when_position_delta_matches_report(self):
        result = reconcile_execution(
            before_cash=1000.0,
            before_positions={"AAPL": 0, "MSFT": 3},
            after_cash=840.0,
            after_positions={"AAPL": 2, "MSFT": 2},
            execution_report=[
                {"ticker": "AAPL", "action": "BUY", "filled": 2},
                {"ticker": "MSFT", "action": "SELL", "filled": 1},
            ],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mismatched"], {})
        self.assertEqual(result["expected_position_delta"]["AAPL"], 2)
        self.assertEqual(result["actual_position_delta"]["MSFT"], -1)

    def test_reconcile_detects_mismatch(self):
        result = reconcile_execution(
            before_cash=1000.0,
            before_positions={"AAPL": 0},
            after_cash=900.0,
            after_positions={"AAPL": 1},
            execution_report=[
                {"ticker": "AAPL", "action": "BUY", "filled": 2},
            ],
        )

        self.assertFalse(result["ok"])
        self.assertIn("AAPL", result["mismatched"])
        self.assertEqual(result["mismatched"]["AAPL"]["expected"], 2)
        self.assertEqual(result["mismatched"]["AAPL"]["actual"], 1)

    def test_reconcile_ignores_invalid_or_unknown_records(self):
        result = reconcile_execution(
            before_cash=1000.0,
            before_positions={"AAPL": 1},
            after_cash=1000.0,
            after_positions={"AAPL": 1},
            execution_report=[
                {"ticker": "XYZ", "action": "BUY", "filled": 5},
                {"ticker": "AAPL", "action": "BUY", "filled": "not-a-number"},
                {"ticker": None, "action": "SELL", "filled": 1},
            ],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mismatched"], {})
        self.assertEqual(result["expected_position_delta"]["AAPL"], 0)


if __name__ == "__main__":
    unittest.main()
