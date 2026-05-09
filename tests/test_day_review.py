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
                    {"ticker": "AMZN", "action": "BUY", "requested": 100, "filled": 100, "avg_fill_price": 10.2, "commission": 1.5, "elapsed_sec": 1.2, "status_detail": "filled_complete", "status": "Filled"},
                    {"ticker": "MU", "action": "BUY", "requested": 50, "filled": 25, "avg_fill_price": 21.0, "commission": 0.75, "elapsed_sec": 4.8, "status_detail": "partial_open", "status": "Partial"},
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
        self.assertAlmostEqual(review["execution_quality"]["fill_notional_ratio"], 1545 / 2000)
        self.assertAlmostEqual(review["execution_quality"]["estimated_slippage_cost"], 45.0)
        self.assertAlmostEqual(review["execution_quality"]["estimated_slippage_bps"], (45.0 / 1545.0) * 10000)
        self.assertAlmostEqual(review["execution_quality"]["reported_commission_total"], 2.25)
        self.assertAlmostEqual(review["execution_quality"]["reported_commission_bps"], (2.25 / 1545.0) * 10000)
        self.assertAlmostEqual(review["execution_quality"]["missed_notional"], 455.0)
        self.assertAlmostEqual(review["execution_quality"]["estimated_total_cost"], 47.25)
        self.assertEqual(review["execution_quality"]["partial_count"], 1)
        self.assertAlmostEqual(review["execution_quality"]["partial_rate"], 0.5)
        self.assertEqual(review["execution_quality"]["problem_order_count"], 0)
        self.assertEqual(review["execution_quality"]["normalized_status_breakdown"]["filled"], 1)
        self.assertEqual(review["execution_quality"]["normalized_status_breakdown"]["partial"], 1)
        self.assertEqual(review["execution_lifecycle"]["filled"], 1)
        self.assertEqual(review["execution_lifecycle"]["partial"], 1)
        self.assertEqual(review["execution_lifecycle"]["terminal_problem_count"], 0)
        self.assertAlmostEqual(review["execution_lifecycle"]["avg_elapsed_sec"], 3.0)
        self.assertAlmostEqual(review["execution_lifecycle"]["max_elapsed_sec"], 4.8)
        self.assertEqual(review["execution_lifecycle"]["timeout_cancel_requested_count"], 0)
        self.assertEqual(review["execution_lifecycle"]["status_detail_breakdown"]["filled_complete"], 1)
        self.assertEqual(review["position_changes"][0]["ticker"], "AMZN")
        self.assertTrue(review["highlights"])

    def test_build_day_review_lifecycle_problem_states(self):
        decision_doc = {
            "date": "2026-05-01",
            "payload": {
                "status": "partial",
                "orders": [
                    {"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 100.0, "amount": 1000.0},
                    {"ticker": "MSFT", "action": "BUY", "shares": 8, "price": 100.0, "amount": 800.0},
                    {"ticker": "NVDA", "action": "BUY", "shares": 5, "price": 100.0, "amount": 500.0},
                ],
                "cash_after": 7700.0,
            },
        }
        ledger_doc = {
            "payload": {
                "before": {"cash": 10000.0, "positions": {}},
                "after": {"cash": 7700.0, "positions": {"AAPL": 10, "MSFT": 2}},
                "execution_report": [
                    {"ticker": "AAPL", "action": "BUY", "requested": 10, "filled": 10, "avg_fill_price": 100.0, "elapsed_sec": 0.9, "status_detail": "filled_complete", "status": "Filled"},
                    {"ticker": "MSFT", "action": "BUY", "requested": 8, "filled": 2, "avg_fill_price": 101.0, "elapsed_sec": 10.5, "timeout_cancel_requested": True, "status_detail": "timeout_partial_then_cancelled", "status": "Submitted_No_Report"},
                    {"ticker": "NVDA", "action": "BUY", "requested": 5, "filled": 0, "avg_fill_price": 0.0, "elapsed_sec": 10.2, "timeout_cancel_requested": True, "status_detail": "timeout_cancelled", "status": "Cancelled"},
                ],
            }
        }

        review = build_day_review(decision_doc=decision_doc, ledger_doc=ledger_doc, latest_metric=None)

        self.assertEqual(review["execution_lifecycle"]["filled"], 1)
        self.assertEqual(review["execution_lifecycle"]["submitted_no_report"], 1)
        self.assertEqual(review["execution_lifecycle"]["cancelled"], 1)
        self.assertEqual(review["execution_lifecycle"]["terminal_problem_count"], 2)
        self.assertAlmostEqual(review["execution_lifecycle"]["terminal_problem_rate"], 2 / 3)
        self.assertEqual(review["execution_lifecycle"]["timeout_cancel_requested_count"], 2)
        self.assertAlmostEqual(review["execution_lifecycle"]["timeout_cancel_requested_rate"], 2 / 3)
        self.assertEqual(review["execution_lifecycle"]["partial_terminal_count"], 1)
        self.assertEqual(review["execution_lifecycle"]["timeout_problem_count"], 2)
        self.assertAlmostEqual(review["execution_lifecycle"]["avg_elapsed_sec"], (0.9 + 10.5 + 10.2) / 3)
        self.assertAlmostEqual(review["execution_lifecycle"]["max_elapsed_sec"], 10.5)
        self.assertEqual(review["execution_lifecycle"]["status_detail_breakdown"]["timeout_partial_then_cancelled"], 1)
        self.assertTrue(any("执行生命周期摘要" in msg for msg in review["highlights"]))
        self.assertTrue(any("执行时延与异常" in msg for msg in review["highlights"]))

    def test_build_day_review_cost_metrics_without_commission_data(self):
        decision_doc = {
            "date": "2026-05-02",
            "payload": {
                "status": "filled",
                "orders": [
                    {"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 100.0, "amount": 1000.0},
                ],
                "cash_after": 9000.0,
            },
        }
        ledger_doc = {
            "payload": {
                "before": {"cash": 10000.0, "positions": {}},
                "after": {"cash": 9000.0, "positions": {"AAPL": 10}},
                "execution_report": [
                    {"ticker": "AAPL", "action": "BUY", "requested": 10, "filled": 10, "avg_fill_price": 100.0, "status": "Filled"},
                ],
            }
        }

        review = build_day_review(decision_doc=decision_doc, ledger_doc=ledger_doc, latest_metric=None)

        self.assertEqual(review["execution_quality"]["reported_commission_total"], 0.0)
        self.assertEqual(review["execution_quality"]["estimated_total_cost"], 0.0)
        self.assertEqual(review["execution_quality"]["missed_notional"], 0.0)
        self.assertEqual(review["execution_quality"]["filled_notional"], 1000.0)

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
