from __future__ import annotations

import json
import threading
import unittest
from urllib.request import Request, urlopen

from .common import APP_ROOT
from http_oa_read.server import create_server


class FakeManager:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"phase": "scan_ready", "session": {"verified": True}}

    def verify_credentials(self, credentials):
        self.calls.append(("verify", credentials))
        return self.snapshot()

    def clear_session(self):
        self.calls.append(("clear",))
        return self.snapshot()

    def scan(self):
        self.calls.append(("scan",))
        return self.snapshot()

    def run(self, max_count, run_mode="finite"):
        self.calls.append(("run", max_count, run_mode))
        return self.snapshot()

    def stop(self):
        self.calls.append(("stop",))
        return self.snapshot()

    def start(self, credentials, max_count, run_mode="finite"):
        self.calls.append(("start", credentials, max_count, run_mode))
        return self.snapshot()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.manager = FakeManager()
        self.server = create_server(APP_ROOT, 0, manager=self.manager)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, path, payload):
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_binds_loopback_and_serves_status_and_page(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with urlopen(f"{self.base_url}/api/status", timeout=2) as response:
            state = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            page = response.read().decode("utf-8")

        self.assertEqual(state["phase"], "scan_ready")
        self.assertIn("OA 已阅助手（HTTP版）", page)

    def test_routes_manual_actions_and_agent_start(self):
        self.post("/api/session/clear", {})
        self.post("/api/session/verify", {"credentials": "Cookie: secret"})
        self.post("/api/scan", {})
        self.post("/api/run", {"maxCount": 20, "runMode": "finite"})
        self.post("/api/stop", {})
        self.post(
            "/api/start",
            {"credentials": "Cookie: secret", "maxCount": 1, "runMode": "all"},
        )

        self.assertEqual(
            self.manager.calls,
            [
                ("clear",),
                ("verify", "Cookie: secret"),
                ("scan",),
                ("run", 20, "finite"),
                ("stop",),
                ("start", "Cookie: secret", 1, "all"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
