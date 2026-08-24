"""OA HTTP 工作台的内存 Session 和批次状态。"""

from __future__ import annotations

import copy
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import ScanSnapshot
from .portal_client import PortalClient, PortalSessionExpired
from .runner import BatchRunner, Event
from .session_keepalive import random_keepalive_interval


RunnerFactory = Callable[..., BatchRunner]
FOREGROUND_PHASES = {"verifying_credentials", "scanning"}


class RunManager:
    def __init__(
        self,
        app_directory: Path,
        client: PortalClient | object | None = None,
        runner_factory: RunnerFactory = BatchRunner,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.app_directory = app_directory.resolve()
        self.client = client or PortalClient(keepalive_interval_factory=keepalive_interval_factory)
        keepalive = getattr(self.client, "keepalive", None)
        if keepalive is not None and client is not None:
            keepalive.interval_factory = keepalive_interval_factory
        self.runner_factory = runner_factory
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._scan_snapshot: ScanSnapshot | None = None
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        return {
            "phase": "waiting_credentials",
            "message": "等待验证 OA 登录凭据",
            "session": {
                "verified": False,
                "verifiedAt": "",
                "cookieCount": 0,
                "keepAlive": self.client.keepalive.status(False) if hasattr(self.client, "keepalive") else {},
            },
            "scan": {
                "scanned": False,
                "current": False,
                "total": 0,
                "eligibleCount": 0,
                "skippedCount": 0,
                "categories": [],
            },
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": ""},
            "results": [],
            "logs": [],
        }

    def _is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _start_keepalive(self) -> None:
        keepalive = getattr(self.client, "keepalive", None)
        check = getattr(self.client, "check_session", None)
        if keepalive is None or not callable(check):
            return
        keepalive.record_success()
        keepalive.start(check, lambda error: isinstance(error, PortalSessionExpired), self._handle_keepalive_expired)

    def _stop_keepalive(self) -> None:
        keepalive = getattr(self.client, "keepalive", None)
        if keepalive is not None:
            keepalive.stop()

    def _handle_keepalive_expired(self) -> None:
        invalidate = getattr(self.client, "invalidate_credentials", None)
        if callable(invalidate):
            invalidate()
        with self._lock:
            self._stop_event.set()
            session = self._state.get("session")
            if isinstance(session, dict):
                session["verified"] = False
            self._state["phase"] = "session_expired"
            self._state["message"] = "保活检查发现 OA 登录凭据已失效，已停止后续请求"
            self._append_log("error", str(self._state["message"]))

    def _append_log(self, level: str, message: str) -> None:
        logs = self._state["logs"]
        assert isinstance(logs, list)
        logs.append(
            {
                "level": level,
                "message": message,
                "time": datetime.now().strftime("%H:%M:%S"),
            }
        )

    def _controls(self, state: dict[str, object]) -> None:
        running = self._is_running()
        foreground_busy = state.get("phase") in FOREGROUND_PHASES
        busy = running or foreground_busy
        session = state.get("session")
        scan = state.get("scan")
        verified = isinstance(session, dict) and bool(session.get("verified"))
        scan_current = isinstance(scan, dict) and bool(scan.get("current"))
        state.update(
            {
                "canVerify": not busy,
                "canScan": verified and not busy,
                "canRun": verified and scan_current and not busy,
                "canStop": running,
                "strictSerial": True,
            }
        )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            keepalive = getattr(self.client, "keepalive", None)
            if isinstance(session, dict) and keepalive is not None:
                session["keepAlive"] = keepalive.status(bool(session.get("verified")))
            self._controls(state)
            return state

    def verify_credentials(self, credential_text: str) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("已阅运行中，不能更换登录凭据")
            if self._state.get("phase") in FOREGROUND_PHASES:
                raise RuntimeError("凭据验证或扫描正在进行")
            self._state["phase"] = "verifying_credentials"
            self._state["message"] = "正在验证 OA 登录凭据"
            self._state["session"] = self._initial_state()["session"]
            self._scan_snapshot = None
            self._state["scan"] = self._initial_state()["scan"]
            self._state["results"] = []
        self._stop_keepalive()

        try:
            summary = self.client.load_credentials(credential_text)  # type: ignore[attr-defined]
        except Exception as error:
            self.client.close()  # type: ignore[attr-defined]
            with self._lock:
                self._state["phase"] = "failed"
                self._state["message"] = str(error) or "OA 登录凭据验证失败"
                self._state["session"] = self._initial_state()["session"]
                self._scan_snapshot = None
                self._state["scan"] = self._initial_state()["scan"]
                self._append_log("error", self._state["message"])
            raise

        with self._lock:
            self._state["session"] = {
                "verified": True,
                "verifiedAt": summary.get("verifiedAt", ""),
                "cookieCount": summary.get("cookieCount", 0),
            }
            self._start_keepalive()
            self._state["phase"] = "credentials_ready"
            self._state["message"] = "OA 登录凭据有效，可以扫描待办"
            self._append_log("success", "OA 登录凭据验证成功")
            state = self.snapshot()
            credentials = str(getattr(self.client, "copyable_credentials", "") or "")
            if credentials:
                state["credentials"] = credentials
            return state

    def clear_session(self) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("已阅运行中，不能清除当前 Session")
            if self._state.get("phase") in FOREGROUND_PHASES:
                raise RuntimeError("凭据验证或扫描正在进行，不能清除当前 Session")
            self._stop_keepalive()
            self.client.close()  # type: ignore[attr-defined]
            self._scan_snapshot = None
            self._state = self._initial_state()
            return self.snapshot()

    def scan(self) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("已阅运行中，不能重新扫描")
            if self._state.get("phase") in FOREGROUND_PHASES:
                raise RuntimeError("凭据验证或扫描正在进行")
            session = self._state.get("session")
            if not isinstance(session, dict) or not session.get("verified"):
                raise RuntimeError("请先验证 OA 登录凭据")
            self._state["phase"] = "scanning"
            self._state["message"] = "正在扫描全部 OA 待办"
            self._scan_snapshot = None
            self._state["scan"] = self._initial_state()["scan"]

        try:
            snapshot = self.client.scan_waiting()  # type: ignore[attr-defined]
        except Exception as error:
            with self._lock:
                self._state["phase"] = "failed"
                self._state["message"] = str(error) or "扫描 OA 待办失败"
                self._scan_snapshot = None
                self._state["scan"] = self._initial_state()["scan"]
                self._append_log("error", self._state["message"])
            raise

        with self._lock:
            self._scan_snapshot = snapshot
            self._state["scan"] = {
                "scanned": True,
                "current": True,
                "total": snapshot.total,
                "eligibleCount": snapshot.eligible_count,
                "skippedCount": snapshot.skipped_count,
                "categories": snapshot.public_categories(),
            }
            self._state["phase"] = "scan_ready"
            self._state["message"] = "扫描完成，只会处理同类公文，其他类型全部跳过"
            self._append_log(
                "success",
                f"扫描完成：共 {snapshot.total} 条，可已阅 {snapshot.eligible_count} 条，跳过 {snapshot.skipped_count} 条",
            )
            return self.snapshot()

    def run(self, max_count: int, run_mode: str = "all") -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("已有已阅批次正在运行")
            if run_mode not in {"finite", "all"}:
                raise ValueError("执行模式必须是指定数量或无限模式")
            if not isinstance(max_count, int) or isinstance(max_count, bool) or max_count < 1:
                raise ValueError("本次数量必须是正整数")
            if self._scan_snapshot is None:
                raise RuntimeError("请先扫描全部待办")
            scan_state = self._state.get("scan")
            if not isinstance(scan_state, dict) or not scan_state.get("current"):
                raise RuntimeError("扫描结果已失效，请重新扫描")
            target_count = (
                self._scan_snapshot.eligible_count
                if run_mode == "all"
                else min(max_count, self._scan_snapshot.eligible_count)
            )
            if target_count < 1:
                raise RuntimeError("当前扫描没有可执行的同类公文")

            self._stop_event.clear()
            self._state["phase"] = "running"
            self._state["message"] = "正在逐条处理 OA 已阅"
            self._state["runMode"] = run_mode
            self._state["results"] = []
            self._state["progress"] = {
                "total": target_count,
                "completed": 0,
                "success": 0,
                "failed": 0,
                "current": "准备开始",
            }
            records = list(self._scan_snapshot.records)
            self._thread = threading.Thread(
                target=self._run_worker,
                args=(records, target_count),
                name="oa-http-read-runner",
                daemon=True,
            )
            self._thread.start()
            return self.snapshot()

    def _run_worker(self, records: list[object], target_count: int) -> None:
        runner = self.runner_factory(self.client, stop_event=self._stop_event, emit=self._apply_event)
        result = runner.run(records, target_count)  # type: ignore[arg-type]
        with self._lock:
            scan = self._state.get("scan")
            if isinstance(scan, dict):
                scan["current"] = False
            if result.session_expired:
                self._stop_keepalive()
                self.client.clear_credentials()  # type: ignore[attr-defined]
                session = self._state.get("session")
                if isinstance(session, dict):
                    session["verified"] = False
                self._state["phase"] = "session_expired"
                self._state["message"] = result.error or "OA 登录凭据已失效，已停止后续请求"
                self._append_log("error", self._state["message"])
            elif result.stopped:
                self._state["phase"] = "terminated"
                self._state["message"] = "已在记录边界终止；重新扫描后可以继续"
                self._append_log("warning", "批次已终止")
            elif result.failed:
                self._state["phase"] = "failed"
                self._state["message"] = result.error or (
                    f"本批处理完成：成功 {result.success} 条，失败 {result.failed} 条；异常项已跳过"
                )
                self._append_log("error", self._state["message"])
            else:
                self._state["phase"] = "completed"
                self._state["message"] = "本批已阅完成；重新扫描后可以继续"
                self._append_log("success", f"本批完成 {result.success} 条")

    def _apply_event(self, event: Event) -> None:
        with self._lock:
            event_type = event.get("type")
            if event_type == "progress":
                self._state["progress"] = {
                    key: event.get(key, "" if key == "current" else 0)
                    for key in ("total", "completed", "success", "failed", "current")
                }
            elif event_type == "record_result":
                result = {key: value for key, value in event.items() if key != "type"}
                results = self._state["results"]
                assert isinstance(results, list)
                results.append(result)
            elif event_type == "log":
                self._append_log(str(event.get("level") or "info"), str(event.get("message") or ""))

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running():
                raise RuntimeError("当前没有运行中的已阅批次")
            self._stop_event.set()
            self._state["phase"] = "stopping"
            self._state["message"] = "将在当前已阅请求完成后的记录边界停止"
            self._append_log("warning", "收到终止请求")
            return self.snapshot()

    def start(
        self,
        credentials: str,
        max_count: int,
        run_mode: str = "all",
    ) -> dict[str, object]:
        if credentials.strip():
            self.verify_credentials(credentials)
        else:
            session = self.snapshot().get("session")
            if not isinstance(session, dict) or not session.get("verified"):
                raise RuntimeError("未提供凭据且当前 Session 未验证")
        self.scan()
        return self.run(max_count=max_count, run_mode=run_mode)

    def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        self._stop_keepalive()
        self.client.close()  # type: ignore[attr-defined]
