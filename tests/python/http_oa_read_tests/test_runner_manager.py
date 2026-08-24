from __future__ import annotations

import time
import threading
import unittest
from pathlib import Path

from .common import APP_ROOT  # noqa: F401
from http_oa_read.manager import RunManager
from http_oa_read.models import ScanSnapshot, WaitingRecord
from http_oa_read.portal_client import PortalBusinessError, PortalSessionExpired
from http_oa_read.runner import BatchRunner


def record(index: int, category="DOC", subcategory="official-document") -> WaitingRecord:
    return WaitingRecord(
        file_id=f"file-{index}",
        title=f"测试标题 {index}",
        file_type_id=f"type-{index}",
        step_item_id=f"step-{index}",
        main_category_code=category,
        sub_category_code=subcategory,
        sub_category_name="测试模块",
    )


class FakePortal:
    def __init__(self):
        self.calls = []
        self.closed = False

    def load_credentials(self, source):
        self.secret = source
        return {"cookieCount": 2, "verifiedAt": "2026-08-21T10:00:00"}

    def scan_waiting(self):
        rows = [record(1), record(2), record(3, "WORKFLOW_PLATFORM", "DI")]
        return ScanSnapshot.from_records(rows, total=3)

    def mark_read(self, item):
        self.calls.append(item.file_id)

    def close(self):
        self.closed = True


class RunnerManagerTests(unittest.TestCase):
    def test_runner_is_strictly_serial_and_never_dispatches_other_categories(self) -> None:
        portal = FakePortal()
        events = []
        rows = [record(1), record(2, "WORKFLOW_PLATFORM", "DI"), record(3)]

        result = BatchRunner(portal, emit=events.append).run(rows, limit=2)

        self.assertEqual(portal.calls, ["file-1", "file-3"])
        self.assertEqual(result.success, 2)
        self.assertEqual(result.skipped, 1)

    def test_runner_stops_before_dispatching_the_next_record(self) -> None:
        stop_event = threading.Event()

        class StopAfterFirstPortal(FakePortal):
            def mark_read(self, item):
                self.calls.append(item.file_id)
                stop_event.set()

        portal = StopAfterFirstPortal()
        result = BatchRunner(portal, stop_event=stop_event).run([record(1), record(2)], limit=2)

        self.assertEqual(portal.calls, ["file-1"])
        self.assertTrue(result.stopped)

    def test_runner_skips_business_code_failure_and_continues(self) -> None:
        class BusinessFailurePortal(FakePortal):
            def mark_read(self, item):
                self.calls.append(item.file_id)
                if item.file_id == "file-1":
                    raise PortalBusinessError("提交 OA 已阅业务码不是 200")

        portal = BusinessFailurePortal()
        events = []
        result = BatchRunner(portal, emit=events.append).run([record(1), record(2)], limit=2)

        self.assertEqual(portal.calls, ["file-1", "file-2"])
        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.stopped)
        record_results = [event for event in events if event.get("type") == "record_result"]
        self.assertEqual([event["status"] for event in record_results], ["失败", "成功"])

    def test_runner_skips_non_session_exception_and_continues(self) -> None:
        class UnexpectedFailurePortal(FakePortal):
            def mark_read(self, item):
                self.calls.append(item.file_id)
                if item.file_id == "file-1":
                    raise RuntimeError("提交 OA 已阅连接被重置")

        portal = UnexpectedFailurePortal()
        result = BatchRunner(portal).run([record(1), record(2)], limit=2)

        self.assertEqual(portal.calls, ["file-1", "file-2"])
        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 1)
        self.assertFalse(result.session_expired)
        self.assertFalse(result.stopped)

    def test_runner_stops_when_session_expires(self) -> None:
        class ExpiredPortal(FakePortal):
            def mark_read(self, item):
                self.calls.append(item.file_id)
                raise PortalSessionExpired("OA 登录会话已失效")

        portal = ExpiredPortal()
        result = BatchRunner(portal).run([record(1), record(2)], limit=2)

        self.assertEqual(portal.calls, ["file-1"])
        self.assertEqual(result.failed, 1)
        self.assertTrue(result.session_expired)
        self.assertFalse(result.stopped)

    def test_manager_defaults_to_all_mode_and_keeps_credentials_private(self) -> None:
        portal = FakePortal()
        manager = RunManager(Path("."), client=portal)
        state = manager.verify_credentials("Cookie: SESSION=secret-value")
        self.assertNotIn("secret-value", str(state))
        scanned = manager.scan()
        self.assertEqual(scanned["scan"]["eligibleCount"], 2)
        self.assertEqual(scanned["scan"]["skippedCount"], 1)

        started = manager.run(max_count=1)
        self.assertEqual(started["phase"], "running")
        finished = self._wait(manager)
        self.assertEqual(finished["phase"], "completed")
        self.assertEqual(finished["progress"]["success"], 2)
        self.assertFalse(finished["scan"]["current"])
        manager.shutdown()
        self.assertTrue(portal.closed)

    def test_verification_network_wait_does_not_block_status_polling(self) -> None:
        started = threading.Event()
        release = threading.Event()

        class BlockingPortal(FakePortal):
            def load_credentials(self, source):
                self.secret = source
                started.set()
                if not release.wait(2):
                    raise RuntimeError("测试未释放验证请求")
                return {"cookieCount": 2, "verifiedAt": "2026-08-21T10:00:00"}

        portal = BlockingPortal()
        manager = RunManager(Path("."), client=portal)
        verify_errors = []
        verify_thread = threading.Thread(
            target=lambda: self._capture_error(verify_errors, manager.verify_credentials, "Cookie: SESSION=secret")
        )
        verify_thread.start()
        self.assertTrue(started.wait(1))

        polled = threading.Event()
        polled_state = {}

        def poll_status():
            polled_state.update(manager.snapshot())
            polled.set()

        poll_thread = threading.Thread(target=poll_status)
        poll_thread.start()
        try:
            self.assertTrue(polled.wait(0.1), "验证网络等待阻塞了状态轮询")
            self.assertEqual(polled_state["phase"], "verifying_credentials")
            self.assertFalse(polled_state["canVerify"])
        finally:
            release.set()
            verify_thread.join(timeout=2)
            poll_thread.join(timeout=2)
            manager.shutdown()
        self.assertFalse(verify_errors)

    def test_verification_failure_enters_failed_state_and_closes_session(self) -> None:
        class RejectingPortal(FakePortal):
            def load_credentials(self, source):
                self.secret = source
                raise RuntimeError("OA 验证请求失败")

        portal = RejectingPortal()
        manager = RunManager(Path("."), client=portal)

        with self.assertRaisesRegex(RuntimeError, "OA 验证请求失败"):
            manager.verify_credentials("Cookie: SESSION=secret")

        state = manager.snapshot()
        self.assertEqual(state["phase"], "failed")
        self.assertIn("OA 验证请求失败", state["message"])
        self.assertFalse(state["session"]["verified"])
        self.assertTrue(portal.closed)

    def test_scan_network_wait_does_not_block_status_polling(self) -> None:
        started = threading.Event()
        release = threading.Event()

        class BlockingScanPortal(FakePortal):
            def scan_waiting(self):
                started.set()
                if not release.wait(2):
                    raise RuntimeError("测试未释放扫描请求")
                return super().scan_waiting()

        portal = BlockingScanPortal()
        manager = RunManager(Path("."), client=portal)
        manager.verify_credentials("Cookie: SESSION=secret")
        scan_errors = []
        scan_thread = threading.Thread(target=lambda: self._capture_error(scan_errors, manager.scan))
        scan_thread.start()
        self.assertTrue(started.wait(1))

        try:
            state = manager.snapshot()
            self.assertEqual(state["phase"], "scanning")
            self.assertFalse(state["canScan"])
        finally:
            release.set()
            scan_thread.join(timeout=2)
            manager.shutdown()
        self.assertFalse(scan_errors)

    def test_agent_start_runs_verify_scan_and_read(self) -> None:
        portal = FakePortal()
        manager = RunManager(Path("."), client=portal)

        state = manager.start("Cookie: SESSION=secret", max_count=2)
        self.assertEqual(state["phase"], "running")
        finished = self._wait(manager)

        self.assertEqual(finished["progress"]["success"], 2)
        self.assertEqual(portal.calls, ["file-1", "file-2"])
        manager.shutdown()

    def test_manager_keeps_running_after_business_code_failure(self) -> None:
        class BusinessFailurePortal(FakePortal):
            def mark_read(self, item):
                self.calls.append(item.file_id)
                if item.file_id == "file-1":
                    raise PortalBusinessError("提交 OA 已阅业务码不是 200")

        portal = BusinessFailurePortal()
        manager = RunManager(Path("."), client=portal)
        manager.verify_credentials("Cookie: SESSION=secret")
        manager.scan()

        manager.run(max_count=2, run_mode="finite")
        finished = self._wait(manager)

        self.assertEqual(portal.calls, ["file-1", "file-2"])
        self.assertEqual(finished["phase"], "failed")
        self.assertEqual(finished["progress"]["success"], 1)
        self.assertEqual(finished["progress"]["failed"], 1)
        self.assertEqual([item["status"] for item in finished["results"]], ["失败", "成功"])
        self.assertIn("异常项已跳过", finished["message"])
        manager.shutdown()

    def test_all_mode_processes_every_eligible_record(self) -> None:
        portal = FakePortal()
        manager = RunManager(Path("."), client=portal)
        manager.verify_credentials("Cookie: SESSION=secret")
        manager.scan()

        manager.run(max_count=1, run_mode="all")
        finished = self._wait(manager)

        self.assertEqual(finished["progress"]["success"], 2)
        self.assertEqual(portal.calls, ["file-1", "file-2"])
        manager.shutdown()

    def test_finite_mode_clamps_requested_count_to_available_records(self) -> None:
        portal = FakePortal()
        manager = RunManager(Path("."), client=portal)
        manager.verify_credentials("Cookie: SESSION=secret")
        manager.scan()

        manager.run(max_count=5000, run_mode="finite")
        finished = self._wait(manager)

        self.assertEqual(finished["progress"]["total"], 2)
        self.assertEqual(finished["progress"]["success"], 2)
        self.assertEqual(portal.calls, ["file-1", "file-2"])
        manager.shutdown()

    def test_clear_session_drops_backend_state_after_page_refresh(self) -> None:
        portal = FakePortal()
        manager = RunManager(Path("."), client=portal)
        manager.verify_credentials("Cookie: SESSION=secret")
        manager.scan()

        state = manager.clear_session()

        self.assertEqual(state["phase"], "waiting_credentials")
        self.assertFalse(state["session"]["verified"])
        self.assertFalse(state["scan"]["scanned"])
        self.assertTrue(portal.closed)

    @staticmethod
    def _wait(manager: RunManager):
        for _ in range(100):
            state = manager.snapshot()
            if state["phase"] in {"completed", "failed", "terminated"}:
                return state
            time.sleep(0.01)
        raise AssertionError("批次没有按时结束")

    @staticmethod
    def _capture_error(errors, action, *args):
        try:
            action(*args)
        except Exception as error:  # pragma: no cover - 只用于线程错误转交
            errors.append(error)


if __name__ == "__main__":
    unittest.main()
