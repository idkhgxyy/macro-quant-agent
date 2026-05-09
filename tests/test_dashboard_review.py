import os
import tempfile
import unittest

from dashboard.server import _resolve_review_paths


class DashboardReviewTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
