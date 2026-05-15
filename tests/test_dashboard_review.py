import os
import tempfile
import unittest

from dashboard.server import _build_review_response, _list_dates, _resolve_review_paths


class DashboardReviewTests(unittest.TestCase):
    def test_list_dates_extracts_sorted_dates_by_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = os.path.join(tmpdir, "ledger")
            os.makedirs(ledger, exist_ok=True)
            open(os.path.join(ledger, "execution_2026-05-10.json"), "w", encoding="utf-8").close()
            open(os.path.join(ledger, "execution_2026-05-08.json"), "w", encoding="utf-8").close()
            open(os.path.join(ledger, "ignore.txt"), "w", encoding="utf-8").close()

            self.assertEqual(_list_dates("execution_", ledger), ["2026-05-08", "2026-05-10"])

    def test_resolve_review_paths_uses_decision_date_for_default_ledger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshots = os.path.join(tmpdir, "snapshots")
            ledger = os.path.join(tmpdir, "ledger")
            os.makedirs(snapshots, exist_ok=True)
            os.makedirs(ledger, exist_ok=True)
            open(os.path.join(snapshots, "decision_2026-05-08.json"), "w", encoding="utf-8").close()
            open(os.path.join(snapshots, "decision_2026-05-09.json"), "w", encoding="utf-8").close()
            open(os.path.join(ledger, "execution_2026-05-08.json"), "w", encoding="utf-8").close()

            decision_path, ledger_path, review_date = _resolve_review_paths(None, snapshots, ledger)

            self.assertEqual(decision_path, os.path.join(snapshots, "decision_2026-05-09.json"))
            self.assertEqual(ledger_path, os.path.join(ledger, "execution_2026-05-09.json"))
            self.assertEqual(review_date, "2026-05-09")

    def test_resolve_review_paths_for_explicit_date(self):
        decision_path, ledger_path, review_date = _resolve_review_paths(
            "2026-05-09",
            "/tmp/snapshots",
            "/tmp/ledger",
        )
        self.assertEqual(decision_path, "/tmp/snapshots/decision_2026-05-09.json")
        self.assertEqual(ledger_path, "/tmp/ledger/execution_2026-05-09.json")
        self.assertEqual(review_date, "2026-05-09")

    def test_build_review_response_includes_auto_brief_and_cognitive_fields(self):
        review = _build_review_response(
            decision_doc={
                "date": "2026-05-14",
                "payload": {
                    "status": "filled",
                    "plan": {
                        "allocations": {"AAPL": 0.2, "MSFT": 0.1},
                        "evidence_weights": {"news": 0.5, "market": 0.3, "sec_edgar": 0.2},
                        "self_evaluation": {
                            "confidence": 0.74,
                            "key_risks": ["短期动量回撤风险"],
                            "counterpoints": ["若宏观转弱，应提高现金"],
                        },
                    },
                    "llm_audit": {"validator_warnings": ["cash_buffer_violation_candidate"]},
                    "retrieval_route": {
                        "focus_sources": ["positions", "market", "sec_edgar"],
                        "avoid_sources": ["news"],
                        "rationale": "当前持仓与市场/公告信号更值得优先参考。",
                    },
                    "orders": [
                        {"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 100.0, "amount": 1000.0},
                    ],
                    "would_submit_preview": [
                        {
                            "ticker": "AAPL",
                            "action": "BUY",
                            "shares": 10,
                            "price": 100.0,
                            "amount": 1000.0,
                            "outside_rth": True,
                            "market_session": "planning_only",
                            "market_orders_currently_allowed": False,
                        }
                    ],
                    "positions_after": {"AAPL": 10},
                    "cash_after": 9000.0,
                },
            },
            ledger_doc={
                "payload": {
                    "before": {"cash": 10000.0, "positions": {}},
                    "after": {"cash": 9000.0, "positions": {"AAPL": 10}},
                    "execution_report": [
                        {
                            "ticker": "AAPL",
                            "action": "BUY",
                            "requested": 10,
                            "filled": 10,
                            "avg_fill_price": 100.0,
                            "status": "Filled",
                        }
                    ],
                }
            },
            latest_metric={"date": "2026-05-14", "turnover": 0.1},
        )

        self.assertIn("auto_brief", review)
        self.assertTrue(review["auto_brief"])
        self.assertTrue(any("总体结论：" in line for line in review["auto_brief"]))
        self.assertTrue(any("证据侧重点：" in line for line in review["auto_brief"]))
        self.assertEqual(review["self_evaluation"]["confidence"], 0.74)
        self.assertEqual(review["top_evidence_weights"][0]["source"], "news")
        self.assertEqual(review["retrieval_route"]["focus_sources"][0], "positions")
        self.assertEqual(review["would_submit_preview"][0]["ticker"], "AAPL")
        self.assertTrue(review["would_submit_preview"][0]["outside_rth"])
        self.assertIn("review_summary", review)
        self.assertEqual(review["review_summary"]["_audit"]["selected_attempt"], "fallback")
        self.assertEqual(review["review_summary_source"], "fallback")

    def test_build_review_response_prefers_report_sidecar_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reports_dir = os.path.join(tmpdir, "reports")
            os.makedirs(reports_dir, exist_ok=True)
            with open(os.path.join(reports_dir, "daily_report_2026-05-14.review.json"), "w", encoding="utf-8") as f:
                f.write(
                    """
{
  "date": "2026-05-14",
  "review_summary": {
    "summary": "这是 sidecar 中的真实复盘摘要。",
    "key_points": ["sidecar key point"],
    "risks": ["sidecar risk"],
    "next_steps": ["sidecar next step"],
    "_audit": {
      "selected_attempt": "initial",
      "prompt_version": "v-test:review"
    }
  },
  "auto_brief": ["总体结论：来自 sidecar。"]
}
                    """.strip()
                )

            with unittest.mock.patch("dashboard.server.ROOT", tmpdir):
                review = _build_review_response(
                    decision_doc={
                        "date": "2026-05-14",
                        "payload": {
                            "status": "filled",
                            "plan": {"allocations": {"AAPL": 0.2}},
                            "cash_after": 9000.0,
                        },
                    },
                    ledger_doc={
                        "payload": {
                            "before": {"cash": 10000.0, "positions": {}},
                            "after": {"cash": 9000.0, "positions": {"AAPL": 10}},
                            "execution_report": [],
                        }
                    },
                    latest_metric={"date": "2026-05-14", "turnover": 0.1},
                    review_date="2026-05-14",
                )

        self.assertEqual(review["review_summary_source"], "report_sidecar")
        self.assertEqual(review["review_summary"]["summary"], "这是 sidecar 中的真实复盘摘要。")
        self.assertEqual(review["auto_brief"][0], "总体结论：来自 sidecar。")


if __name__ == "__main__":
    unittest.main()
