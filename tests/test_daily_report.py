import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from reports.generate_daily_report import _review_sidecar_path, generate_daily_report


@contextmanager
def _isolated_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        try:
            yield tmpdir
        finally:
            os.chdir(old_cwd)


class DailyReportTests(unittest.TestCase):
    def test_generate_daily_report_includes_llm_review_fallback_section(self):
        date_str = "2026-05-14"
        with _isolated_cwd() as tmpdir:
            os.makedirs("metrics", exist_ok=True)
            os.makedirs("snapshots", exist_ok=True)
            os.makedirs("ledger", exist_ok=True)

            with open(os.path.join("metrics", "metrics.jsonl"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"date": date_str, "status": "filled", "llm_valid": True, "llm_sec": 1.2}) + "\n")

            with open(os.path.join("snapshots", f"decision_{date_str}.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "date": date_str,
                        "payload": {
                            "status": "filled",
                            "plan": {
                                "allocations": {"AAPL": 0.2, "MSFT": 0.1},
                                "selected_strategies": ["core_hold_momentum_tilt"],
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
                                "avoid_sources": [],
                                "rationale": "当前持仓与市场/公告信号更值得优先参考。",
                            },
                            "orders": [
                                {"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 100.0, "amount": 1000.0},
                            ],
                            "positions_after": {"AAPL": 10},
                            "cash_after": 9000.0,
                            "reconciliation": {"ok": True},
                        },
                    },
                    f,
                    ensure_ascii=False,
                )

            with open(os.path.join("ledger", f"execution_{date_str}.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
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
                    f,
                    ensure_ascii=False,
                )

            with patch("reports.generate_daily_report.VOLCENGINE_API_KEY", None), patch(
                "reports.generate_daily_report.VOLCENGINE_MODEL_ENDPOINT",
                None,
            ):
                out_path = generate_daily_report(date_str)

            self.assertEqual(out_path, os.path.join("reports", f"daily_report_{date_str}.md"))
            with open(os.path.join(tmpdir, out_path), "r", encoding="utf-8") as f:
                report_text = f.read()
            with open(os.path.join(tmpdir, _review_sidecar_path(date_str)), "r", encoding="utf-8") as f:
                review_sidecar = json.load(f)

            self.assertIn("## Auto Brief", report_text)
            self.assertIn("总体结论：", report_text)
            self.assertIn("证据侧重点：", report_text)
            self.assertIn("风险提示：", report_text)
            self.assertIn("后续关注：", report_text)
            self.assertIn("## LLM Review", report_text)
            self.assertIn("- summary:", report_text)
            self.assertIn("- review_generation_mode: fallback", report_text)
            self.assertIn("- key_point:", report_text)
            self.assertIn("review_summary", review_sidecar)
            self.assertIn("auto_brief", review_sidecar)
            self.assertTrue(review_sidecar["auto_brief"])
            self.assertEqual(review_sidecar["review_summary"]["_audit"]["selected_attempt"], "fallback")


if __name__ == "__main__":
    unittest.main()
