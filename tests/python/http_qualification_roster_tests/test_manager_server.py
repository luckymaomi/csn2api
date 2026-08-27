from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

try:
    from .common import APP_ROOT, PORTAL_PERSON_HEADERS, person_row  # noqa: F401
except ImportError:
    from common import APP_ROOT, PORTAL_PERSON_HEADERS, person_row  # type: ignore[no-redef]  # noqa: F401

from http_qualification_roster.exporter import RosterWorkbook
from http_qualification_roster.manager import RunManager
from http_qualification_roster.server import create_server
from ieb_protocol.roster_models import FilterField, OperatingQualification, SelectOption


class FakeKeepAlive:
    def __init__(self) -> None:
        self.interval_factory = lambda: 30
        self.started = False

    def status(self, verified: bool) -> dict[str, object]:
        return {"active": self.started and verified}

    def record_success(self) -> None:
        return None

    def start(self, *_args: object) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False


class FakeClient:
    def __init__(self) -> None:
        self.keepalive = FakeKeepAlive()
        self.verified = False
        self.copyable_credentials = "JSESSIONID=hidden; iebJSid=hidden"
        self.load_metadata_calls = 0

    def load_credentials(self, source: str) -> dict[str, object]:
        if not source:
            raise ValueError("缺少凭据")
        self.verified = True
        return {
            "verifiedAt": "2026-08-27 09:00:00",
            "identity": {"staffNumber": "900001", "name": "测试用户"},
        }

    def load_metadata(self) -> tuple[list[FilterField], list[OperatingQualification]]:
        self.require_credentials()
        self.load_metadata_calls += 1
        return (
            [
                FilterField("fleetCdToArray", "执飞机型", True, [SelectOption("777", "B777")]),
                FilterField("activeStatusArray", "在职状态", True, [SelectOption("ZAIZHI", "在职")]),
            ],
            [OperatingQualification("RAMA", "北美区域单飞资格")],
        )

    def require_credentials(self) -> None:
        if not self.verified:
            raise RuntimeError("未验证")

    def check_session(self) -> None:
        self.require_credentials()

    def query_roster(self, _filters: object, _code: str) -> tuple[int, list[str]]:
        self.require_credentials()
        return 1, list(PORTAL_PERSON_HEADERS)

    def export_people(self, _filters: object, _code: str, columns: list[str]) -> list[dict[str, str]]:
        self.require_credentials()
        source = person_row()
        return [{column: source.get(column, "") for column in columns}]

    def invalidate_credentials(self) -> None:
        self.verified = False

    def clear_credentials(self) -> None:
        self.verified = False
        self.keepalive.stop()

    def close(self) -> None:
        return None


class ManagerServerTests(unittest.TestCase):
    def test_verification_and_metadata_loading_are_separate_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            manager = RunManager(Path(directory), client=client)  # type: ignore[arg-type]
            verified = manager.verify_credentials("Cookie: fake")
            self.assertTrue(verified["session"]["verified"])
            self.assertFalse(verified["metadata"]["loaded"])
            self.assertEqual(verified["filterFields"], [])
            self.assertEqual(verified["qualifications"], [])
            self.assertEqual(client.load_metadata_calls, 0)
            with self.assertRaisesRegex(RuntimeError, "先加载门户筛选"):
                manager.start_query({"filters": {}, "qualificationCodes": ["RAMA"]})

            loaded = manager.load_metadata()
            self.assertTrue(loaded["metadata"]["loaded"])
            self.assertEqual(len(loaded["filterFields"]), 2)
            self.assertEqual([item["code"] for item in loaded["qualifications"]], ["RAMA"])
            self.assertEqual(client.load_metadata_calls, 1)
            manager.shutdown()

    def test_loopback_server_exposes_independent_metadata_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            manager = RunManager(Path(directory), client=client)  # type: ignore[arg-type]
            server = create_server(APP_ROOT, 0, manager)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            try:
                verified = self._post(host, port, "/api/session/verify", {"credentials": "Cookie: fake"})
                self.assertFalse(verified["metadata"]["loaded"])
                loaded = self._post(host, port, "/api/metadata/load", {})
                self.assertTrue(loaded["metadata"]["loaded"])
                html = urllib.request.urlopen(f"http://{host}:{port}/", timeout=5).read().decode("utf-8")
                self.assertIn('id="loadFiltersButton"', html)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                manager.shutdown()

    def test_completed_query_exposes_full_dynamic_rows_and_excel_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=FakeClient())  # type: ignore[arg-type]
            try:
                manager.verify_credentials("Cookie: fake")
                manager.load_metadata()
                manager.start_query({
                    "filters": {"fleetCdToArray": ["777"], "activeStatusArray": ["ZAIZHI"]},
                    "qualificationCodes": ["RAMA"],
                })
                deadline = time.monotonic() + 5
                state = manager.snapshot()
                while state["phase"] == "querying" and time.monotonic() < deadline:
                    time.sleep(0.01)
                    state = manager.snapshot()

                self.assertEqual(state["phase"], "completed")
                self.assertEqual(state["resultColumns"], PORTAL_PERSON_HEADERS)
                self.assertEqual(state["results"], [{
                    "sequence": 1,
                    "fields": person_row(),
                    "qualificationCode": "RAMA",
                }])
                target = manager.download_path()
                self.assertIsNotNone(target)
                self.assertEqual(
                    RosterWorkbook(target).read_headers(),  # type: ignore[arg-type]
                    ["序号", *PORTAL_PERSON_HEADERS, "资质类别"],
                )
            finally:
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
