from __future__ import annotations

import threading
import unittest
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-lock-entry-helper"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from http_lock_entry.session_keepalive import SessionKeepAlive


class SessionKeepAliveTests(unittest.TestCase):
    def test_waits_then_runs_read_only_check_and_stops_cleanly(self) -> None:
        checked = threading.Event()
        keepalive = SessionKeepAlive(lambda: 1, 1, "test-cookie-keepalive")

        keepalive.start(checked.set, lambda _error: False, lambda: None)
        self.assertTrue(checked.wait(2))

        keepalive.record_success()
        state = keepalive.status(True)
        self.assertEqual(state["state"], "healthy")
        self.assertTrue(state["running"])
        self.assertGreaterEqual(state["nextIntervalSeconds"], 1)

        keepalive.stop()
        self.assertEqual(keepalive.status(True)["state"], "stopped")
        self.assertFalse(keepalive.status(True)["running"])


if __name__ == "__main__":
    unittest.main()
