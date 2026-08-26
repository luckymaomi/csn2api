from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    from .common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # type: ignore[no-redef]  # noqa: F401
from ieb_protocol.qualification_monitor_models import QualificationGroup, QualificationItem
from http_qualification_monitor.manager import RunManager
from http_qualification_monitor.server import create_server


GROUPS = [
    QualificationGroup(parent["msgType"], parent["msgCode"], [
        QualificationItem(child["msgType"], child["msgCode"])
        for child in parent["sonList"]
    ])
    for parent in CLASSIFICATION_PAYLOAD
]


class FakeClient:
    def __init__(self) -> None:
        self.verified = False

    def load_credentials(self, source: str) -> tuple[dict[str, object], list[QualificationGroup]]:
        if not source:
            raise ValueError("缺少凭据")
        self.verified = True
        return {
            "cookieCount": 2,
            "verifiedAt": "2026-08-23T10:00:00",
            "qualificationCount": 4,
            "identity": {"staffNumber": "900001", "name": "测试用户"},
        }, GROUPS

    def require_credentials(self) -> None:
        if not self.verified:
            raise RuntimeError("未验证")

    def export_qualification(self, code: str) -> bytes:
        time.sleep(0.005)
        return ooxml_bytes(code)

    def clear_credentials(self) -> None:
        self.verified = False

    def close(self) -> None:
        return None


def wait_finished(manager: RunManager) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = manager.snapshot()
        if state["phase"] in {"completed", "partial_failure", "stopped", "session_expired", "failed"}:
            return state
        time.sleep(0.01)
    raise AssertionError("任务未结束")


class ManagerServerTests(unittest.TestCase):
    def test_manager_never_returns_credentials_and_registers_download_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=FakeClient())  # type: ignore[arg-type]
            state = manager.verify_credentials("Cookie: secret-value")
            self.assertEqual(state["session"]["identity"]["name"], "测试用户")
            self.assertNotIn("secret-value", json.dumps(state, ensure_ascii=False))
            manager.export_all()
            finished = wait_finished(manager)
            self.assertEqual(finished["phase"], "completed")
            self.assertEqual(finished["progress"]["success"], 4)
            archive_id = finished["downloads"]["archiveId"]
            self.assertTrue(manager.download_path(archive_id).is_file())
            self.assertIsNone(manager.download_path("../../cookie.txt"))
            manager.shutdown()

    def test_loopback_server_exposes_workflow_and_controlled_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=FakeClient())  # type: ignore[arg-type]
            server = create_server(APP_ROOT, 0, manager)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            try:
                self.assertEqual(host, "127.0.0.1")
                html = urllib.request.urlopen(f"http://{host}:{port}/", timeout=5).read()
                self.assertIn("资质监控（皇帝版）".encode("utf-8"), html)
                verified = self._post(host, port, "/api/session/verify", {"credentials": "Cookie: fake"})
                self.assertEqual(verified["phase"], "ready")
                self._post(host, port, "/api/export/one", {"qualType": "90D3F"})
                finished = wait_finished(manager)
                file_id = finished["items"][0]["downloadId"]
                body = urllib.request.urlopen(f"http://{host}:{port}/api/download/{file_id}", timeout=5).read()
                self.assertTrue(body.startswith(b"PK"))
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(f"http://{host}:{port}/api/download/unknown", timeout=5)
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                manager.shutdown()

    @staticmethod
    def _post(host: str, port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"http://{host}:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
