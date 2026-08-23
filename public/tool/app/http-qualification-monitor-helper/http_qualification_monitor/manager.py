from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exporter import NativeExportStore
from .models import ExportSummary, QualificationGroup
from .portal_client import PortalClient, PortalSessionExpired
from .runner import ExportRunner
from .session_keepalive import random_keepalive_interval


SECRET_PATTERN = re.compile(r"(?i)(JSESSIONID|iebJSid)\s*=\s*[^;\s]+")
FINAL_PHASES = {"completed", "partial_failure", "stopped", "session_expired", "failed"}


def _safe_error(error: Exception) -> str:
    return SECRET_PATTERN.sub(r"\1=[已隐藏]", str(error) or error.__class__.__name__)


class RunManager:
    def __init__(
        self,
        output_directory: Path,
        client: PortalClient | None = None,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.output_directory = Path(output_directory)
        self.client = client or PortalClient(keepalive_interval_factory=keepalive_interval_factory)
        keepalive = getattr(self.client, "keepalive", None)
        if keepalive is not None and client is not None:
            keepalive.interval_factory = keepalive_interval_factory
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._groups: list[QualificationGroup] = []
        self._downloads: dict[str, Path] = {}
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        return {
            "phase": "waiting_credentials",
            "session": {
                "verified": False,
                "verifiedAt": "",
                "keepAlive": self.client.keepalive.status(False) if hasattr(self.client, "keepalive") else {},
            },
            "groups": [],
            "items": [],
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0},
            "current": None,
            "downloads": {"archiveId": None},
            "logs": [],
            "error": "",
        }

    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

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
            self._state["error"] = "保活检查发现登录凭据已失效，已停止后续导出"
            self._log("error", self._state["error"])

    def _log(self, level: str, message: str) -> None:
        logs = self._state["logs"]
        assert isinstance(logs, list)
        logs.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "message": SECRET_PATTERN.sub(r"\1=[已隐藏]", message),
        })
        del logs[:-100]

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            keepalive = getattr(self.client, "keepalive", None)
            if isinstance(session, dict) and keepalive is not None:
                session["keepAlive"] = keepalive.status(bool(session.get("verified")))
            return state

    def verify_credentials(self, source: str) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("导出任务进行中，不能重新验证凭据")
            self._state["phase"] = "verifying"
            self._state["error"] = ""
        self._stop_keepalive()
        try:
            summary, groups = self.client.load_credentials(source)
        except Exception as error:
            with self._lock:
                self._groups = []
                self._state = self._initial_state()
                self._state["error"] = _safe_error(error)
                self._log("error", "登录凭据验证失败")
            raise
        with self._lock:
            self._groups = groups
            self._state = self._initial_state()
            self._state["phase"] = "ready"
            self._state["session"] = {"verified": True, **summary}
            self._state["groups"] = [
                {
                    "name": group.name,
                    "code": group.code,
                    "items": [{"name": item.name, "code": item.code} for item in group.items],
                }
                for group in groups
            ]
            self._state["items"] = self._new_item_states(groups)
            self._start_keepalive()
            self._log("success", f"已加载 {summary['qualificationCount']} 个资质子类")
            return self.snapshot()

    @staticmethod
    def _new_item_states(groups: list[QualificationGroup]) -> list[dict[str, object]]:
        return [
            {
                "groupCode": group.code,
                "groupName": group.name,
                "code": item.code,
                "name": item.name,
                "status": "pending",
                "error": "",
                "downloadId": None,
                "fileName": "",
            }
            for group in groups
            for item in group.items
        ]

    def _start(self, code: str | None) -> dict[str, object]:
        with self._lock:
            self.client.require_credentials()
            if self._running():
                raise RuntimeError("已有导出任务正在执行")
            if code is not None and sum(item.code == code for group in self._groups for item in group.items) != 1:
                raise ValueError("未知资质子类")
            selected = [item for item in self._new_item_states(self._groups) if code is None or item["code"] == code]
            self._state["items"] = selected
            self._state["progress"] = {"total": len(selected), "completed": 0, "success": 0, "failed": 0}
            self._state["current"] = None
            self._state["downloads"] = {"archiveId": None}
            self._state["phase"] = "exporting"
            self._state["error"] = ""
            self._stop_event.clear()
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            self._thread = threading.Thread(target=self._worker, args=(run_id, code), daemon=True)
            self._thread.start()
            return self.snapshot()

    def export_all(self) -> dict[str, object]:
        return self._start(None)

    def export_one(self, code: str) -> dict[str, object]:
        return self._start(str(code or "").strip())

    def start(self, credentials: str) -> dict[str, object]:
        self.verify_credentials(credentials)
        return self.export_all()

    def _worker(self, run_id: str, code: str | None) -> None:
        try:
            store = NativeExportStore(self.output_directory, run_id)
            runner = ExportRunner(self.client, store, self._handle_event, self._stop_event.is_set)
            summary = runner.run_all(self._groups) if code is None else runner.run_one(self._groups, code)
            self._finish(summary)
        except Exception as error:
            with self._lock:
                self._state["phase"] = "failed"
                self._state["error"] = _safe_error(error)
                self._state["current"] = None
                self._log("error", "导出任务异常结束")

    def _item_state(self, code: str) -> dict[str, object] | None:
        items = self._state["items"]
        assert isinstance(items, list)
        return next((item for item in items if item["code"] == code), None)

    def _handle_event(self, event: dict[str, object]) -> None:
        with self._lock:
            code = str(event.get("code", ""))
            item = self._item_state(code)
            if item is None:
                return
            event_type = event.get("type")
            if event_type == "item_started":
                item["status"] = "running"
                self._state["current"] = {"code": code, "name": item["name"]}
                self._log("info", f"正在导出 {item['name']}")
            elif event_type == "item_succeeded":
                path = Path(event["path"])  # type: ignore[arg-type]
                file_id = uuid.uuid4().hex
                self._downloads[file_id] = path.resolve()
                item.update({"status": "success", "downloadId": file_id, "fileName": path.name})
                self._increment_progress(success=True)
                self._log("success", f"已完成 {item['name']}")
            elif event_type == "item_failed":
                item.update({"status": "failed", "error": str(event.get("error", "导出失败"))})
                self._increment_progress(success=False)
                self._log("error", f"{item['name']} 导出失败")

    def _increment_progress(self, *, success: bool) -> None:
        progress = self._state["progress"]
        assert isinstance(progress, dict)
        progress["completed"] = int(progress["completed"]) + 1
        key = "success" if success else "failed"
        progress[key] = int(progress[key]) + 1

    def _finish(self, summary: ExportSummary) -> None:
        with self._lock:
            self._state["current"] = None
            if summary.archive is not None:
                file_id = uuid.uuid4().hex
                self._downloads[file_id] = summary.archive.resolve()
                self._state["downloads"] = {"archiveId": file_id, "archiveName": summary.archive.name}
            if summary.session_expired:
                self.client.clear_credentials()
                session = self._state["session"]
                assert isinstance(session, dict)
                session["verified"] = False
                self._state["phase"] = "session_expired"
                self._log("error", "登录会话已失效，任务已停止")
            elif summary.interrupted:
                self._state["phase"] = "stopped"
                self._log("info", "任务已在当前请求完成后停止")
            elif summary.failed:
                self._state["phase"] = "partial_failure"
                self._log("error", "批次存在失败项，未生成完整 ZIP")
            else:
                self._state["phase"] = "completed"
                self._log("success", "导出任务已完成")

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._running():
                return self.snapshot()
            self._stop_event.set()
            self._state["phase"] = "stopping"
            self._log("info", "已请求停止，将在当前请求返回后生效")
            return self.snapshot()

    def download_path(self, file_id: str) -> Path | None:
        with self._lock:
            path = self._downloads.get(str(file_id or ""))
            return path if path is not None and path.is_file() else None

    def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        self._stop_keepalive()
        self.client.close()
