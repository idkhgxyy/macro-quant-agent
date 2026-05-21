"""Tests for PersistenceService: snapshot, ledger, metrics, portfolio-state persistence."""
import json
import os
import tempfile
import unittest

from core.persistence import PersistenceService


class PersistenceServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._cwd = os.getcwd()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)

    def test_save_and_load_decision_snapshot(self):
        PersistenceService.save_decision_snapshot("2026-05-20", {"status": "filled", "reasoning": "test"})
        loaded = PersistenceService.load_decision_snapshot("2026-05-20")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.get("payload", {}).get("status"), "filled")

    def test_load_decision_snapshot_returns_none_when_missing(self):
        loaded = PersistenceService.load_decision_snapshot("2099-01-01")
        self.assertIsNone(loaded)

    def test_save_rag_snapshot(self):
        PersistenceService.save_rag_snapshot("2026-05-20", {"macro": "test macro"})
        path = os.path.join("snapshots", "rag_2026-05-20.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc["payload"]["macro"], "test macro")

    def test_save_execution_ledger(self):
        PersistenceService.save_execution_ledger("2026-05-20", {"before": {"cash": 10000.0}})
        path = os.path.join("ledger", "execution_2026-05-20.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc["payload"]["before"]["cash"], 10000.0)

    def test_save_portfolio_state(self):
        PersistenceService.save_portfolio_state(50000.0, {"AAPL": 100})
        self.assertTrue(os.path.exists("portfolio_state.json"))

    def test_append_metrics(self):
        PersistenceService.append_metrics({"date": "2026-05-20", "status": "filled", "turnover": 0.25})
        self.assertTrue(os.path.exists(os.path.join("metrics", "metrics.jsonl")))


if __name__ == "__main__":
    unittest.main()
