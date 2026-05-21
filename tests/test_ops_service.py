"""Tests for OpsService: heartbeat, kill switch, alerting, events."""
import os
import tempfile
import unittest

from core.ops import OpsService


class OpsServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._cwd = os.getcwd()
        os.environ["RUNTIME_STATE_DIR"] = os.path.join(self._tmpdir, "runtime")
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._cwd)
        os.environ.pop("RUNTIME_STATE_DIR", None)

    def test_check_kill_switch_returns_unlocked_by_default(self):
        result = OpsService.check_kill_switch()
        self.assertFalse(result["locked"])

    def test_trigger_and_check_kill_switch(self):
        OpsService.trigger_kill_switch(reason="test_reason", source="test_source")
        result = OpsService.check_kill_switch()
        self.assertTrue(result["locked"])
        self.assertEqual(result["reason"], "test_reason")
        self.assertEqual(result["source"], "test_source")

    def test_start_and_finish_run(self):
        run = OpsService.start_run(run_mode="test", date_str="2026-05-20", broker="mock", live_trading_enabled=False)
        self.assertIn("run_id", run)
        self.assertIn("started_at", run)
        run_id = run.get("run_id", "")
        OpsService.finish_run(run_id=run_id, status="filled", error=None)
        self.assertTrue(os.path.exists("runtime/heartbeat.json"))

    def test_emit_event(self):
        OpsService.emit_event("test", "INFO", "unit_test", "ops service test event")
        events_path = os.path.join("events", "events.jsonl")
        self.assertTrue(os.path.exists(events_path))

    def test_evaluate_and_notify_returns_dict(self):
        result = OpsService.evaluate_and_notify(
            date_str="2026-05-20",
            broker="mock",
            status="filled",
            run_start_ts="2026-05-20T00:00:00Z",
            run_end_ts="2026-05-20T00:01:00Z",
        )
        self.assertIn("triggered", result)
        self.assertIn("reason", result)
        self.assertIn("items", result)

    def test_check_kill_switch_custom_lock_path(self):
        result = OpsService.check_kill_switch(lock_path="custom.lock")
        self.assertFalse(result["locked"])


if __name__ == "__main__":
    unittest.main()
