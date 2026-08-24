"""In-memory session and batch lifecycle for SOC positioning."""

from __future__ import annotations

import base64
import copy
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .input_data import read_input
from .models import InputPayload
from .portal_client import PortalSessionExpired, SocPortalClient
from .result_store import ResultStore
from .runner import BatchRunner
from .session_keepalive import random_keepalive_interval


class RunManager:
    def __init__(
        self,
        app_directory: Path,
        client: SocPortalClient | None = None,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ):
        self.app_directory = app_directory.resolve()
        self.client = client or SocPortalClient(keepalive_interval_factory=keepalive_interval_factory)
        if client is not None and hasattr(self.client, "keepalive"):
            self.client.keepalive.interval_factory = keepalive_interval_factory
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.result_path: Path | None = None
        self.state: dict[str, object] = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        return {"phase": "waiting_credentials", "message": "等待验证 SOC 凭据", "session": {"verified": False, "verifiedAt": "", "cookieCount": 0, "keepAlive": self.client.keepalive.status(False)}, "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": ""}, "checks": {"checked": False, "validCount": 0, "invalidCount": 0, "errors": []}, "results": [], "logs": [], "downloads": {"result": False}}

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            value = copy.deepcopy(self.state)
            session = value["session"]
            session["keepAlive"] = self.client.keepalive.status(bool(session["verified"]))
            value.update({"canVerify": not self._running(), "canCheckData": bool(value["session"]["verified"]) and not self._running(), "canRun": bool(value["session"]["verified"]) and not self._running(), "canStop": self._running()})
            return value

    def _running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def _log(self, level: str, message: str) -> None:
        self.state["logs"].append({"level": level, "message": message, "time": datetime.now().strftime("%H:%M:%S")})

    def verify(self, credentials: str) -> dict[str, object]:
        with self.lock:
            if self._running():
                raise RuntimeError("批次运行中不能更换凭据")
            self.state["phase"], self.state["message"] = "verifying_credentials", "正在验证 SOC 凭据"
            self._log("info", "正在连接 SOC 并验证随机置位页面")
        self.client.keepalive.stop()
        try:
            info = self.client.load_credentials(credentials)
        except Exception as error:
            self.client.clear_credentials()
            with self.lock:
                self.state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0}
                self.state["phase"] = "waiting_credentials"
                self._log("error", str(error))
            raise
        with self.lock:
            self.state["session"] = {"verified": True, **info}
            self.client.keepalive.record_success()
            self.client.keepalive.start(
                self.client.check_session,
                lambda error: isinstance(error, PortalSessionExpired),
                self._handle_keepalive_expired,
            )
            self.state["phase"], self.state["message"] = "credentials_ready", "SOC 凭据有效"
            self._log("success", "SOC 凭据验证成功")
            result = self.snapshot()
            result["credentials"] = self.client.copyable_credentials
            return result

    def _handle_keepalive_expired(self) -> None:
        self.client.invalidate_credentials()
        with self.lock:
            self.stop_event.set()
            self.state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0}
            self.state["phase"] = "session_expired"
            self.state["message"] = "保活检查发现 SOC 会话已失效，已停止后续录入"
            self._log("error", str(self.state["message"]))

    def _parse(self, payload: InputPayload) -> tuple[list[dict[str, object]], list[str]]:
        return read_input(payload)

    def check_data(self, payload: InputPayload) -> dict[str, object]:
        with self.lock:
            if not self.state["session"]["verified"]:
                raise PortalSessionExpired("请先验证 SOC 凭据")
            if self._running():
                raise RuntimeError("批次运行中不能检查数据")
        records, errors = self._parse(payload)
        with self.lock:
            self.state["checks"] = {"checked": True, "ok": bool(records) and not errors, "validCount": len(records), "invalidCount": len(errors), "errors": errors}
            self.state["phase"], self.state["message"] = "data_checked", f"数据检查完成：有效 {len(records)} 条，无效 {len(errors)} 条"
            for error in errors:
                self._log("warning", error)
            return self.snapshot()

    def _emit(self, event: dict[str, object]) -> None:
        with self.lock:
            if event.get("type") == "progress":
                self.state["progress"] = {key: event.get(key, 0 if key != "current" else "") for key in ("total", "completed", "success", "failed", "current")}
            elif event.get("type") == "record_result":
                result = {key: value for key, value in event.items() if key != "type"}
                self.state["results"].append(result)
            elif event.get("type") == "log":
                self._log(str(event.get("level", "info")), str(event.get("message", "")))

    def run(self, payload: InputPayload) -> dict[str, object]:
        with self.lock:
            if self._running():
                raise RuntimeError("已有批次正在录入")
            if not self.state["session"]["verified"]:
                raise PortalSessionExpired("请先验证 SOC 凭据")
        records, errors = self._parse(payload)
        if not records:
            raise ValueError("没有可录入的有效数据")
        run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        store = ResultStore(self.app_directory / "results", run_id)
        with self.lock:
            self.result_path = store.path
            self.stop_event = threading.Event()
            self.state.update({"phase": "running", "message": f"开始录入 {len(records)} 条有效数据", "runId": run_id, "results": [], "checks": {"checked": True, "ok": not errors, "validCount": len(records), "invalidCount": len(errors), "errors": errors}, "downloads": {"result": True}})
            self.thread = threading.Thread(target=self._worker, args=(records, store), daemon=True)
            self.thread.start()
            return self.snapshot()

    def _worker(self, records: list[dict[str, object]], store: ResultStore) -> None:
        try:
            summary = BatchRunner(self.client, store, self.stop_event, self._emit).run(records)
            with self.lock:
                stopped = bool(summary.get("stopped"))
                self.state["phase"] = "terminated" if stopped else "completed"
                self.state["message"] = "批次已终止" if stopped else f"录入完成：成功 {summary['success']} 条，失败 {summary['failed']} 条"
                self._log("warning" if stopped else "success", str(self.state["message"]))
        except PortalSessionExpired as error:
            self.client.clear_credentials()
            with self.lock:
                self.state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0}
                self.state["phase"], self.state["message"] = "session_expired", str(error)
                self._log("error", str(error))
        finally:
            store.close()

    def stop(self) -> dict[str, object]:
        with self.lock:
            if not self._running():
                self.state["phase"], self.state["message"] = "terminated", "当前没有运行中的批次"
                return self.snapshot()
            self.stop_event.set()
            self.state["phase"], self.state["message"] = "stopping", "正在终止当前批次"
        self.thread.join(timeout=5)  # type: ignore[union-attr]
        return self.snapshot()

    def download_path(self) -> Path | None:
        return self.result_path if self.result_path and self.result_path.is_file() else None

    def shutdown(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.client.close()
