import unittest

from utils.review import build_day_review


class DayReviewTests(unittest.TestCase):
    def test_build_day_review_with_execution(self):
        decision_doc = {
            "date": "2026-04-28",
            "payload": {
                "status": "filled",
                "plan": {
                    "selected_strategies": ["core_hold_momentum_tilt"],
                    "allocations": {"AMZN": 0.1, "MU": 0.1, "GOOGL": 0.15},
                },
                "orders": [
                    {"ticker": "AMZN", "action": "BUY", "shares": 100, "price": 10.0, "amount": 1000.0},
                    {"ticker": "MU", "action": "BUY", "shares": 50, "price": 20.0, "amount": 1000.0},
                ],
                "positions_after": {"AMZN": 100, "MU": 50, "GOOGL": 10},
                "cash_after": 8000.0,
                "reconciliation": {"ok": True},
            },
        }
        ledger_doc = {
            "payload": {
                "before": {"cash": 10000.0, "positions": {"AMZN": 0, "MU": 0, "GOOGL": 10}},
                "after": {"cash": 8000.0, "positions": {"AMZN": 100, "MU": 50, "GOOGL": 10}},
                "execution_report": [
                    {"ticker": "AMZN", "action": "BUY", "requested": 100, "filled": 100, "avg_fill_price": 10.2, "status": "Filled"},
                    {"ticker": "MU", "action": "BUY", "requested": 50, "filled": 25, "avg_fill_price": 21.0, "status": "Partial"},
                ],
            }
        }
        metric = {"turnover": 0.25, "llm_valid": True, "prompt_version": "v1"}

        review = build_day_review(decision_doc=decision_doc, ledger_doc=ledger_doc, latest_metric=metric)

        self.assertEqual(review["status"], "filled")
        self.assertAlmostEqual(review["target_cash_ratio"], 0.65)
        self.assertEqual(review["cash_delta"], -2000.0)
        self.assertTrue(review["reconcile_ok"])
        self.assertEqual(review["execution_quality"]["executed_order_count"], 2)
        self.assertAlmostEqual(review["execution_quality"]["fill_ratio"], 125 / 150)
        self.assertAlmostEqual(review["execution_quality"]["estimated_slippage_cost"], 45.0)
        self.assertEqual(review["position_changes"][0]["ticker"], "AMZN")
        self.assertTrue(review["highlights"])

    def test_build_day_review_for_planning_only(self):
        decision_doc = {
            "date": "2026-04-30",
            "payload": {
                "status": "planning_only",
                "planning_only_reason": "live_trading_disabled",
                "plan": {"allocations": {"AAPL": 0.2}},
                "market_session": {"market_state": "open", "session_reason": "in_window"},
                "positions_after": {"AAPL": 0},
                "cash_after": 10000.0,
            },
        }

        review = build_day_review(decision_doc=decision_doc, ledger_doc=None, latest_metric=None)

        self.assertEqual(review["status"], "planning_only")
        self.assertEqual(review["planning_only_reason"], "live_trading_disabled")
        self.assertIn("本次仅生成计划", review["highlights"][0])


if __name__ == "__main__":
    unittest.main()
