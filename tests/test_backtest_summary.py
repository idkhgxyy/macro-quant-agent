import unittest

from run_llm_backtest import build_backtest_summary, select_backtest_dates


class BacktestSummaryTests(unittest.TestCase):
    def test_select_backtest_dates_returns_last_n(self):
        dates = list(range(10))
        self.assertEqual(list(select_backtest_dates(dates, 4)), [6, 7, 8, 9])

    def test_build_summary_marks_demo_only_when_using_synthetic_prices(self):
        summary = build_backtest_summary(
            price_source="synthetic",
            used_synthetic_prices=True,
            requested_days=20,
            actual_days=20,
            snapshot_found_days=5,
            snapshot_missing_dates=["2026-01-01"],
            price_period="6mo",
        )

        self.assertEqual(summary["credibility"], "demo_only")
        self.assertIn("used_synthetic_prices", summary["warnings"])
        self.assertIn("missing_rag_snapshots", summary["warnings"])
        self.assertAlmostEqual(summary["snapshot_coverage_ratio"], 0.25)

    def test_build_summary_marks_partial_snapshot_coverage(self):
        summary = build_backtest_summary(
            price_source="yfinance",
            used_synthetic_prices=False,
            requested_days=20,
            actual_days=20,
            snapshot_found_days=16,
            snapshot_missing_dates=["2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"],
            price_period="6mo",
        )

        self.assertEqual(summary["credibility"], "partial_snapshot_coverage")
        self.assertNotIn("used_synthetic_prices", summary["warnings"])


if __name__ == "__main__":
    unittest.main()
