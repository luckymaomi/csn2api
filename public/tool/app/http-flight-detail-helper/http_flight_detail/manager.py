from __future__ import annotations

import base64
import copy
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exporter import ResultExporter
from .input_data import read_input
from .models import Event, InputPayload, MonthOutcome, QueryRecord
from .portal_client import PortalClient, PortalSessionExpired
from .runner import BatchRunner
from .result_store import ResultStore
from .session_keepalive import random_keepalive_interval


class RunManager:
    def __init__(
        self,
        app_directory: Path,
        client: PortalClient | object | None = None,
        runner_factory: Callable[..., BatchRunner] = BatchRunner,
        exporter_factory: Callable[..., ResultExporter] = ResultExporter,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
        checkpoint_interval: int = 20,
    ) -> None:
        self.app_directory = app_directory.resolve()
        self.client = client or PortalClient(keepalive_interval_factory=keepalive_interval_factory)
        self.runner_factory = runner_factory
        self.exporter_factory = exporter_factory
        self.checkpoint_interval = max(1, int(checkpoint_interval))
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._download: Path | None = None
        self._expired_by_keepalive = False
        self._results = ResultStore()
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        keepalive = getattr(self.client, "keepalive", None)
        return {
            "phase": "waiting_credentials",
            "message": "等待验证登录凭据",
            "queryMode": "按人员和月份严格串行",
            "session": {
                "verified": False, "verifiedAt": "", "cookieCount": 0, "identity": None,
                "keepAlive": keepalive.status(False) if keepalive else {},
            },
            "checks": {"data": {"checked": False, "ok": False, "validCount": 0, "invalidCount": 0, "monthCount": 0, "errors": []}},
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": ""},
            "resultTable": self._results.metadata(),
            "logs": [],
            "downloads": {"result": False},
        }

    def _is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _append_log(self, level: str, message: str) -> None:
        self._state["logs"].append({"level": level, "message": message, "time": datetime.now().strftime("%H:%M:%S")})  # type: ignore[union-attr]

    def _set_unverified(self) -> None:
        self._state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0, "identity": None, "keepAlive": {}}

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            keepalive = getattr(self.client, "keepalive", None)
            if isinstance(session, dict) and keepalive:
                session["keepAlive"] = keepalive.status(bool(session.get("verified")))
            running = self._is_running()
            verified = bool(state["session"]["verified"])  # type: ignore[index]
            state.update({
                "canVerify": not running,
                "canCheckData": verified and not running,
                "canRun": verified and not running,
                "canStop": running,
            })
            return state

    def results_page(self, kind: str = "status", offset: int = 0, limit: int = 50) -> dict[str, object]:
        with self._lock:
            return self._results.page(kind, offset, limit)

    def _start_keepalive(self) -> None:
        keepalive = getattr(self.client, "keepalive", None)
        check = getattr(self.client, "check_session", None)
        if not keepalive or not callable(check):
            return
        keepalive.record_success()
        keepalive.start(check, lambda error: isinstance(error, PortalSessionExpired), self._handle_keepalive_expired)

    def _handle_keepalive_expired(self) -> None:
        with self._lock:
            self._expired_by_keepalive = True
            self._stop_event.set()
            self._set_unverified()
            self._state["phase"] = "session_expired"
            self._state["message"] = "登录凭据已失效，已停止后续查询"
            self._append_log("error", str(self._state["message"]))

    def verify_credentials(self, credential_text: str) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("查询运行中，不能更换登录凭据")
            self._state["phase"] = "verifying_credentials"
            self._state["message"] = "正在验证登录凭据"
        try:
            summary = self.client.load_credentials(credential_text)  # type: ignore[attr-defined]
        except Exception:
            with self._lock:
                self._set_unverified()
                self._state["phase"] = "waiting_credentials"
            raise
        with self._lock:
            self._state["session"] = {
                "verified": True,
                "verifiedAt": summary.get("verifiedAt", ""),
                "cookieCount": summary.get("cookieCount", 0),
                "identity": summary.get("identity"),
                "keepAlive": {},
            }
            self._state["phase"] = "credentials_ready"
            self._state["message"] = "登录凭据有效，月度明细接口已就绪"
            self._append_log("success", "凭据验证成功")
            self._start_keepalive()
            state = self.snapshot()
            credentials = str(getattr(self.client, "copyable_credentials", "") or "")
            if credentials:
                state["credentials"] = credentials
            return state

    def _require_session(self) -> None:
        if not self._state["session"]["verified"]:  # type: ignore[index]
            raise RuntimeError("请先验证登录凭据")
        self.client.require_credentials()  # type: ignore[attr-defined]

    @staticmethod
    def payload_from_json(payload: dict[str, object]) -> InputPayload:
        encoded = str(payload.get("excelBase64", "") or "")
        try:
            excel_bytes = base64.b64decode(encoded, validate=True) if encoded else None
        except ValueError as error:
            raise ValueError("Excel 文件内容不是有效 Base64") from error
        return InputPayload(
            input_mode=str(payload.get("inputMode", "excel") or "excel"),
            excel_name=str(payload.get("excelName", "") or ""),
            excel_bytes=excel_bytes,
            pasted_text=str(payload.get("pastedText", "") or ""),
        )

    def _parse(self, payload: InputPayload) -> tuple[list[QueryRecord], list[str]]:
        return read_input(payload)

    def check_data(self, payload: InputPayload) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("查询运行中，不能检查另一批数据")
            self._require_session()
        records, errors = self._parse(payload)
        month_count = sum(len(record.months()) for record in records)
        with self._lock:
            check = {
                "checked": True, "ok": bool(records) and not errors,
                "validCount": len(records), "invalidCount": len(errors),
                "monthCount": month_count, "errors": errors,
            }
            self._state["checks"] = {"data": check}
            self._state["phase"] = "data_checked"
            self._state["message"] = f"数据检查完成：{len(records)} 人，{month_count} 个人员/月，无效 {len(errors)} 条"
            return self.snapshot()

    def check_data_from_json(self, payload: dict[str, object]) -> dict[str, object]:
        return self.check_data(self.payload_from_json(payload))

    def _handle_event(self, event: Event) -> None:
        with self._lock:
            if event.get("type") == "progress":
                self._state["progress"] = {key: event.get(key, "" if key == "current" else 0) for key in ("total", "completed", "success", "failed", "current")}
            elif event.get("type") == "month_result":
                self._results.add(event)
                self._state["resultTable"] = self._results.metadata()

    def _worker(self, records: list[QueryRecord], input_errors: list[str], run_id: str) -> None:
        exporter = self.exporter_factory(self.app_directory / "results" / run_id, run_id)
        latest_outcomes: list[MonthOutcome] = []
        last_flushed = 0

        def checkpoint(outcomes: list[MonthOutcome], force: bool = False) -> None:
            nonlocal latest_outcomes, last_flushed
            latest_outcomes = outcomes
            exporter.add_input_errors(input_errors)
            if not force and len(outcomes) - last_flushed < self.checkpoint_interval:
                return
            exporter.append_batch(outcomes)
            path = exporter.flush()
            last_flushed = len(outcomes)
            with self._lock:
                if path.is_file():
                    self._download = path
                    self._state["downloads"] = {"result": True}

        runner = self.runner_factory(self.client, stop_event=self._stop_event, emit=self._handle_event, checkpoint=checkpoint)
        try:
            result = runner.run(records)
            checkpoint(result.outcomes, force=True)
            finalize = getattr(exporter, "finalize", None)
            if callable(finalize):
                path = finalize(records, input_errors)
                with self._lock:
                    self._download = path
                    self._state["downloads"] = {"result": True}
            with self._lock:
                self._state["progress"] = {
                    "total": len(result.outcomes), "completed": len(result.outcomes),
                    "success": result.success, "failed": result.failed, "current": "",
                }
                if result.session_expired or self._expired_by_keepalive:
                    self.client.clear_credentials()  # type: ignore[attr-defined]
                    self._set_unverified()
                    self._state["phase"] = "session_expired"
                    self._state["message"] = "登录凭据已失效，已保存当前结果"
                elif result.stopped:
                    self._state["phase"] = "terminated"
                    self._state["message"] = "查询已终止，当前结果已保存"
                else:
                    self._state["phase"] = "completed"
                    self._state["message"] = f"查询完成：成功 {result.success}，失败 {result.failed}"
        except Exception as error:  # noqa: BLE001 - 后台任务必须落状态
            with self._lock:
                self._state["phase"] = "failed"
                self._state["message"] = f"批次查询失败：{error}"
                self._append_log("error", str(self._state["message"]))
        finally:
            # 无论完成、停止还是异常，都把当前批次落盘并关闭工作簿。
            try:
                if last_flushed < len(latest_outcomes):
                    exporter.append_batch(latest_outcomes)
                    exporter.flush()
                    last_flushed = len(latest_outcomes)
                finalize = getattr(exporter, "finalize", None)
                if callable(finalize):
                    path = finalize(records, input_errors)
                    with self._lock:
                        self._download = path
                        self._state["downloads"] = {"result": True}
                elif not self._download:
                    path = exporter.flush()
                    if path.is_file():
                        with self._lock:
                            self._download = path
                            self._state["downloads"] = {"result": True}
            finally:
                exporter.close()

    def run(self, payload: InputPayload) -> dict[str, object]:
        with self._lock:
            if self._is_running():
                raise RuntimeError("已有批次正在查询")
            self._require_session()
        records, errors = self._parse(payload)
        if not records:
            raise ValueError("没有可查询的有效数据")
        run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        total = sum(len(record.months()) for record in records)
        with self._lock:
            self._stop_event = threading.Event()
            self._download = None
            self._expired_by_keepalive = False
            self._state.update({
                "phase": "running", "message": f"开始查询 {len(records)} 人、{total} 个人员/月",
                "runId": run_id,
                "progress": {"total": total, "completed": 0, "success": 0, "failed": 0, "current": ""},
                "logs": [], "downloads": {"result": False},
                "checks": {"data": {"checked": True, "ok": not errors, "validCount": len(records), "invalidCount": len(errors), "monthCount": total, "errors": errors}},
            })
            self._results.reset()
            self._state["resultTable"] = self._results.metadata()
            self._thread = threading.Thread(target=self._worker, args=(records, errors, run_id), name="http-flight-detail-runner", daemon=True)
            self._thread.start()
            return self.snapshot()

    def run_from_json(self, payload: dict[str, object]) -> dict[str, object]:
        return self.run(self.payload_from_json(payload))

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._is_running():
                return self.snapshot()
            self._state["phase"] = "stopping"
            self._state["message"] = "正在等待当前请求结束"
            self._stop_event.set()
            thread = self._thread
        thread.join(timeout=5)
        return self.snapshot()

    def download_path(self) -> Path | None:
        with self._lock:
            return self._download if self._download and self._download.is_file() else None

    def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        keepalive = getattr(self.client, "keepalive", None)
        if keepalive:
            keepalive.stop()
        self.client.close()  # type: ignore[attr-defined]
