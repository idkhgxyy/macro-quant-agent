import os
import tempfile
import unittest
from datetime import datetime

from run_scheduler import compute_next_run_at, should_trigger_daily_run
from utils.heartbeat import HeartbeatStore


class HeartbeatStoreTests(unittest.TestCase):
    def test_start_and_finish_run_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "heartbeat.json")
            store = HeartbeatStore(path=path, recent_limit=5)

            run = store.start_run(
                run_mode="manual",
                date_str="2026-05-04",
                broker="mock",
                live_trading_enabled=False,
            )
            running_doc = store.load()
            self.assertEqual(running_doc["current"]["status"], "running")
            self.assertEqual(running_doc["current"]["run_id"], run["run_id"])

            summary = store.finish_run(
                run["run_id"],
                status="planning_only",
                extra={"market_state": "closed"},
            )
            done_doc = store.load()
            self.assertIsNone(done_doc["current"])
            self.assertEqual(done_doc["last_run"]["status"], "planning_only")
            self.assertEqual(done_doc["last_run"]["market_state"], "closed")
            self.assertEqual(done_doc["recent_runs"][0]["run_id"], run["run_id"])
            self.assertIn("duration_sec", summary)
            self.assertEqual(done_doc["last_success"]["status"], "planning_only")

    def test_finish_run_with_error_does_not_replace_last_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "heartbeat.json")
            store = HeartbeatStore(path=path, recent_limit=5)

            first = store.start_run(
                run_mode="manual",
                date_str="2026-05-04",
                broker="mock",
                live_trading_enabled=False,
            )
            store.finish_run(first["run_id"], status="no_trade")

            second = store.start_run(
                run_mode="scheduled",
                date_str="2026-05-05",
                broker="mock",
                live_trading_enabled=False,
            )
            store.finish_run(second["run_id"], status="exception", error="boom")

            doc = store.load()
            self.assertEqual(doc["last_run"]["status"], "exception")
            self.assertEqual(doc["last_run"]["error"], "boom")
            self.assertEqual(doc["last_success"]["status"], "no_trade")

    def test_scheduler_state_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "heartbeat.json")
            store = HeartbeatStore(path=path, recent_limit=5)
            scheduler = store.update_scheduler(
                enabled=True,
                loop_status="waiting",
                schedule_time="16:10",
                timezone="America/New_York",
                poll_seconds=30,
                next_run_at="2026-05-05T16:10:00-04:00",
                last_run_date="2026-05-04",
                message="scheduler idle",
            )
            self.assertTrue(scheduler["enabled"])
            self.assertEqual(scheduler["loop_status"], "waiting")
            self.assertEqual(store.load()["scheduler"]["last_run_date"], "2026-05-04")


class SchedulerTimingTests(unittest.TestCase):
    def test_compute_next_run_same_day(self):
        now = datetime.fromisoformat("2026-05-04T15:00:00-04:00")
        next_run = compute_next_run_at(now, "16:10")
        self.assertEqual(next_run.isoformat(), "2026-05-04T16:10:00-04:00")

    def test_compute_next_run_rolls_to_next_day(self):
        now = datetime.fromisoformat("2026-05-04T16:11:00-04:00")
        next_run = compute_next_run_at(now, "16:10")
        self.assertEqual(next_run.isoformat(), "2026-05-05T16:10:00-04:00")

    def test_should_trigger_daily_run_only_once(self):
        now = datetime.fromisoformat("2026-05-04T16:10:05-04:00")
        self.assertTrue(should_trigger_daily_run(now, "16:10", last_run_date="2026-05-03"))
        self.assertFalse(should_trigger_daily_run(now, "16:10", last_run_date="2026-05-04"))


if __name__ == "__main__":
    unittest.main()
