from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from .common import APP_ROOT  # noqa: F401
from http_flight_detail.manager import RunManager
from http_flight_detail.server import create_server


class KeepAliveStub:
    def status(self, ready):
        return {"running": ready, "state": "healthy" if ready else "stopped"}

    def record_success(self):
        return None

    def start(self, *_args):
        return None

    def stop(self):
        return None


class ClientStub:
    def __init__(self):
        self.keepalive = KeepAliveStub()
        self.copyable_credentials = "JSESSIONID=secret; iebJSid=secret"

    def load_credentials(self, _source):
        return {"verifiedAt": "2026-09-01T10:00:00", "cookieCount": 2, "identity": {"staffNumber": "900000", "name": "测试用户"}}

    def require_credentials(self):
        return None

    def check_session(self):
        return None

    def load_timeline(self, _record):
        return [{"dateType": "1", "start": "2026", "fleet": "32A"}]

    def query_month(self, _record, month, _timeline):
        headers = ["序号", "航班号", "机型", "日期", "左座", "右座", "操纵", "观察", "离场", "到达", "飞行时间", "夜航", "飞行阶段", "人工飞行时间", "人工飞行方式"]
        return headers, [{header: ("1" if header == "序号" else month if header == "日期" else "") for header in headers}]

    def clear_credentials(self):
        return None

    def close(self):
        return None


class ExporterStub:
    instances = []

    def __init__(self, output_directory, _run_id):
        self.path = Path(output_directory) / "result.xlsx"
        self.append_sizes = []
        self.flush_count = 0
        self.closed = False
        self.__class__.instances.append(self)

    def add_input_errors(self, _errors):
        return None

    def append_batch(self, outcomes):
        self.append_sizes.append(len(outcomes))

    def flush(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"result")
        self.flush_count += 1
        return self.path

    def finalize(self, *_args):
        return self.path

    def close(self):
        self.closed = True


class ManagerServerTests(unittest.TestCase):
    def test_checkpoint_writes_are_batched_and_finalized(self) -> None:
        ExporterStub.instances.clear()
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=ClientStub(), exporter_factory=ExporterStub, checkpoint_interval=2)
            manager.verify_credentials("secret")
            manager.run_from_json({"inputMode": "paste", "pastedText": "员工号\t姓名\t开始年月\t结束年月\n900001\t示例甲\t2026/1\t2026/3"})
            manager._thread.join(timeout=5)
            exporter = ExporterStub.instances[0]
            self.assertEqual(exporter.flush_count, 2)
            self.assertEqual(exporter.append_sizes, [2, 3])
            self.assertTrue(exporter.closed)
            manager.shutdown()

    def test_manager_runs_four_column_payload_and_publishes_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=ClientStub())
            manager.verify_credentials("secret")
            payload = {
                "inputMode": "paste",
                "pastedText": "员工号\t姓名\t开始年月\t结束年月\n900001\t示例甲\t2026/1\t2026/2",
            }
            checked = manager.check_data_from_json(payload)
            self.assertEqual(checked["checks"]["data"]["monthCount"], 2)
            manager.run_from_json(payload)
            deadline = time.monotonic() + 5
            while manager.snapshot()["phase"] not in {"completed", "failed"} and time.monotonic() < deadline:
                time.sleep(0.01)
            state = manager.snapshot()
            self.assertEqual(state["phase"], "completed")
            self.assertEqual(state["progress"]["success"], 2)
            self.assertTrue(state["downloads"]["result"])
            self.assertNotIn("secret", json.dumps(state, ensure_ascii=False))
            self.assertTrue(manager.download_path().is_file())
            manager.shutdown()

    def test_loopback_server_serves_status_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=ClientStub())
            server = create_server(APP_ROOT, 0, manager)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            try:
                for route in ("/", "/app.mjs", "/styles.css", "/session_keepalive.mjs", "/theme.js", "/theme.css", "/libs/bootstrap.min.css"):
                    with urllib.request.urlopen(f"http://{host}:{port}{route}", timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertGreater(len(response.read()), 20)
                with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=5) as response:
                    state = json.loads(response.read().decode("utf-8"))
                self.assertEqual(state["phase"], "waiting_credentials")
                with urllib.request.urlopen(f"http://{host}:{port}/api/results?kind=detail&offset=0&limit=10", timeout=5) as response:
                    page = json.loads(response.read().decode("utf-8"))
                self.assertEqual(page["kind"], "detail")
                self.assertEqual(page["rows"], [])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                manager.shutdown()


if __name__ == "__main__":
    unittest.main()
