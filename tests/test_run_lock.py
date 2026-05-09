import json
import os
import socket
import tempfile
import unittest

from utils.heartbeat import HeartbeatStore, utc_now_z
from utils.run_lock import RunLock


class RunLockTests(unittest.TestCase):
    def test_second_acquire_is_blocked_while_lock_is_active(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "agent_run.lock")
            lock = RunLock(path=path, stale_after_seconds=3600)

            first = lock.acquire(owner_id="owner-1", run_mode="manual", date_str="2026-05-09")
            self.assertTrue(first["acquired"])

            second = lock.acquire(owner_id="owner-2", run_mode="scheduled", date_str="2026-05-09")
            self.assertFalse(second["acquired"])
            self.assertEqual(second["reason"], "already_running")
            self.assertEqual(second["existing"]["owner_id"], "owner-1")

            self.assertTrue(lock.release("owner-1"))

    def test_stale_lock_is_recovered_and_heartbeat_current_is_cleared(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "agent_run.lock")
            heartbeat_path = os.path.join(tmpdir, "heartbeat.json")
            store = HeartbeatStore(path=heartbeat_path, recent_limit=5)

            run = store.start_run(
                run_mode="scheduled",
                date_str="2026-05-09",
                broker="mock",
                live_trading_enabled=False,
            )
            doc = store.load()
            doc["current"]["pid"] = 999999
            doc["current"]["host"] = socket.gethostname()
            store.save(doc)

            stale_payload = {
                "owner_id": "stale-owner",
                "component": "daily_agent",
                "run_mode": "scheduled",
                "date": "2026-05-09",
                "pid": 999999,
                "host": socket.gethostname(),
                "acquired_at": utc_now_z(),
            }
            with open(lock_path, "w", encoding="utf-8") as f:
                json.dump(stale_payload, f)

            lock = RunLock(path=lock_path, stale_after_seconds=3600)
            result = lock.acquire(
                owner_id="fresh-owner",
                run_mode="manual",
                date_str="2026-05-09",
                heartbeat_store=store,
            )
            self.assertTrue(result["acquired"])
            self.assertTrue(result["stale_recovered"])

            recovered = store.load()
            self.assertIsNone(recovered["current"])
            self.assertEqual(recovered["last_run"]["run_id"], run["run_id"])
            self.assertEqual(recovered["last_run"]["status"], "stale_recovered")
            self.assertTrue(recovered["last_run"]["stale_recovered"])

            self.assertTrue(lock.release("fresh-owner"))

    def test_live_local_pid_lock_is_not_expired_by_age_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "agent_run.lock")
            stale_payload = {
                "owner_id": "live-owner",
                "component": "daily_agent",
                "run_mode": "manual",
                "date": "2026-05-09",
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "acquired_at": "2020-01-01T00:00:00Z",
            }
            with open(lock_path, "w", encoding="utf-8") as f:
                json.dump(stale_payload, f)

            lock = RunLock(path=lock_path, stale_after_seconds=60)
            result = lock.acquire(owner_id="owner-2", run_mode="scheduled", date_str="2026-05-09")

            self.assertFalse(result["acquired"])
            self.assertEqual(result["reason"], "already_running")
            self.assertIsNone(result["stale_reason"])
            self.assertEqual(result["existing"]["owner_id"], "live-owner")


if __name__ == "__main__":
    unittest.main()
