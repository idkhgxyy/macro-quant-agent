import os
import tempfile
import unittest

from utils.kill_switch import KillSwitchStore


class KillSwitchStateTests(unittest.TestCase):
    def test_trigger_writes_structured_state_and_lock_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "kill_switch.lock")
            state_path = os.path.join(tmpdir, "kill_switch.json")
            store = KillSwitchStore(lock_path=lock_path, state_path=state_path)

            doc = store.trigger(
                reason="alert_policy:exception:1/1",
                source="alert.policy",
                trigger_event={"status": "exception", "date": "2026-05-04"},
            )

            self.assertTrue(doc["locked"])
            self.assertEqual(doc["reason"], "alert_policy:exception:1/1")
            self.assertEqual(doc["source"], "alert.policy")
            self.assertEqual(doc["trigger_event"]["status"], "exception")
            self.assertTrue(os.path.exists(lock_path))
            self.assertTrue(os.path.exists(state_path))

            loaded = store.load()
            self.assertTrue(loaded["lock_file_present"])
            self.assertEqual(loaded["history"][0]["action"], "triggered")

    def test_clear_removes_lock_and_marks_state_unlocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "kill_switch.lock")
            state_path = os.path.join(tmpdir, "kill_switch.json")
            store = KillSwitchStore(lock_path=lock_path, state_path=state_path)

            store.trigger(reason="boom", source="agent.exception")
            cleared = store.clear(reason="manual_clear_after_fix")

            self.assertFalse(cleared["locked"])
            self.assertFalse(os.path.exists(lock_path))
            self.assertEqual(cleared["history"][0]["action"], "cleared")
            self.assertEqual(cleared["history"][0]["reason"], "manual_clear_after_fix")

    def test_legacy_lock_file_is_reflected_in_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "kill_switch.lock")
            state_path = os.path.join(tmpdir, "kill_switch.json")
            with open(lock_path, "w", encoding="utf-8") as f:
                f.write("Kill Switch Triggered Reason: legacy failure\n")

            store = KillSwitchStore(lock_path=lock_path, state_path=state_path)
            doc = store.load()

            self.assertTrue(doc["locked"])
            self.assertTrue(doc["lock_file_present"])
            self.assertEqual(doc["source"], "legacy_lock_file")
            self.assertIn("legacy failure", str(doc["reason"]))


if __name__ == "__main__":
    unittest.main()
