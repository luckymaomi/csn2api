from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path

from ieb_protocol.training_arrangement_models import TrainingOption, TrainingWindow

from .common import SHARED_ROOT  # noqa: F401
from http_training_arrangement.area_defaults import AREA_DEFAULTS
from http_training_arrangement.manager import RunManager


def wait_until_finished(manager: RunManager) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = manager.snapshot()
        if state["phase"] in {"completed", "failed", "terminated", "session_expired"}:
            return state
        time.sleep(0.02)
    raise AssertionError("查询没有按时结束")


class FakeClient:
    def __init__(self) -> None:
        self.verified = False
        self.closed = False
        self.keepalive = type("KeepAlive", (), {"interval_factory": staticmethod(lambda: 30), "status": lambda _self, _ready: {}, "stop": lambda _self: None, "record_success": lambda _self: None, "start": lambda _self, *_args: None})()

    def load_credentials(self, source: str) -> dict[str, object]:
        if not source:
            raise ValueError("缺少凭据")
        self.verified = True
        return {"cookieCount": 2, "cookieNames": ["JSESSIONID", "iebJSid"], "verifiedAt": "2026-09-10T00:00:00", "identity": {"staffNumber": "900001", "name": "测试用户"}}

    def require_credentials(self) -> None:
        if not self.verified:
            raise RuntimeError("请先验证登录凭据")

    def load_options(self) -> list[TrainingOption]:
        return [TrainingOption("jzdjxlCD", "机长等级训练C转D")]

    def query(self, query_input, emit=None):
        if emit:
            emit({"period": "year", "label": "年", "start": "2026-01-01", "end": "2026-09-10"})
            emit({"page": 1, "rows": 1})
        return [TrainingWindow("year", "年", date(2026, 1, 1), date(2026, 9, 10), ["训练科目"], [{"训练科目": "机长等级训练C转D"}], 1, 1)]

    def invalidate_credentials(self) -> None:
        self.verified = False

    def clear_credentials(self) -> None:
        self.verified = False

    def close(self) -> None:
        self.closed = True


class ManagerTests(unittest.TestCase):
    def test_initial_state_exposes_the_default_area_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=FakeClient())  # type: ignore[arg-type]
            try:
                catalog = manager.snapshot()["areaDefaults"]["categories"]
                self.assertEqual([item["name"] for item in catalog], [item.name for item in AREA_DEFAULTS])
                self.assertEqual(
                    sum(len(item["subjects"]) for item in catalog),
                    sum(len(item.subjects) for item in AREA_DEFAULTS),
                )
            finally:
                manager.shutdown()

    def test_verify_load_query_and_excel_download_keep_credentials_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            manager = RunManager(Path(directory), client=client)  # type: ignore[arg-type]
            verified = manager.verify_credentials("Cookie: JSESSIONID=secret; iebJSid=secret-two")
            self.assertTrue(verified["session"]["verified"])
            self.assertNotIn("secret", str(verified))
            manager.load_metadata()
            running = manager.run({"category": "jzdjxlCD", "dateRange": "year", "endDate": "2026-09-10"})
            self.assertEqual(running["phase"], "running")
            finished = wait_until_finished(manager)
            self.assertEqual(finished["phase"], "completed")
            self.assertEqual(len(finished["results"]), 1)
            self.assertTrue(finished["downloads"]["excel"])
            download_id = finished["downloads"]["excelId"]
            self.assertTrue(manager.download_path(str(download_id)).is_file())
            manager.shutdown()
            self.assertTrue(client.closed)

    def test_area_default_mode_queries_all_categories_and_publishes_summary(self) -> None:
        class AreaClient(FakeClient):
            def load_options(self):
                return [TrainingOption(f"code-{index}", subject) for index, subject in enumerate(
                    subject for category in AREA_DEFAULTS for subject in category.subjects
                )]

            def query(self, query_input, emit=None):
                if emit:
                    for key, label in (("week", "周"), ("month", "月"), ("year", "年")):
                        emit({"period": key, "label": label, "start": "2026-01-01", "end": "2026-09-10"})
                        emit({"page": 1, "rows": 1})
                return [
                    TrainingWindow(key, label, date(2026, 1, 1), date(2026, 9, 10), ["训练科目", "训练状态"], [{"训练科目": query_input.category, "训练状态": "完成"}], 1, 1)
                    for key, label in (("week", "周"), ("month", "月"), ("year", "年"))
                ]

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=AreaClient())  # type: ignore[arg-type]
            manager.verify_credentials("Cookie: fake")
            loaded = manager.load_metadata()
            self.assertTrue(loaded["areaDefaults"]["available"])
            manager.run({"mode": "area-default", "endDate": "2026-09-10"})
            finished = wait_until_finished(manager)
            self.assertEqual(finished["phase"], "completed")
            self.assertEqual(len(finished["summary"]), len(AREA_DEFAULTS))
            self.assertEqual(finished["summary"][0]["week"]["rate"], 100.0)
            manager.shutdown()

    def test_area_default_results_are_visible_while_later_subjects_are_running(self) -> None:
        second_started = threading.Event()
        release_second = threading.Event()

        class LiveClient(FakeClient):
            def __init__(self) -> None:
                super().__init__()
                self.calls = 0

            def load_options(self):
                return [TrainingOption(f"code-{index}", subject) for index, subject in enumerate(
                    subject for category in AREA_DEFAULTS for subject in category.subjects
                )]

            def query(self, query_input, emit=None):
                self.calls += 1
                if self.calls == 2:
                    second_started.set()
                    release_second.wait(timeout=3)
                values = []
                for key, label in (("week", "周"), ("month", "月"), ("year", "年")):
                    if emit:
                        emit({"period": key, "label": label, "start": "2026-01-01", "end": "2026-09-10"})
                        emit({"page": 1, "rows": 1})
                    values.append(TrainingWindow(
                        key, label, date(2026, 1, 1), date(2026, 9, 10),
                        ["训练状态"], [{"训练状态": "完成"}], 1, 1,
                    ))
                return values

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), client=LiveClient())  # type: ignore[arg-type]
            try:
                manager.verify_credentials("Cookie: fake")
                manager.load_metadata()
                manager.run({"mode": "area-default", "endDate": "2026-09-10"})
                self.assertTrue(second_started.wait(timeout=2))
                live = manager.snapshot()
                self.assertEqual(live["phase"], "running")
                self.assertEqual(len(live["results"]), 1)
                self.assertEqual(live["results"][0]["total"], 1)
                self.assertEqual(len(live["summary"]), 1)
                self.assertEqual(live["progress"]["completedSubjects"], 1)
            finally:
                release_second.set()
                wait_until_finished(manager)
                manager.shutdown()


if __name__ == "__main__":
    unittest.main()
