from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exporter import ResultExporter
from .models import PilotRecord
from .portal_client import PortalClient, PortalSessionExpired
from .runner import BatchRunner


class RunManager:
    def __init__(self, app_directory: Path, client: PortalClient | None = None) -> None:
        self.app_directory = app_directory.resolve()
        self.client = client or PortalClient()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._path: Path | None = None
        self._records: list[PilotRecord] = []
        self._state: dict[str, object] = {
            "phase": "waiting_credentials", "message": "等待验证登录凭据",
            "session": {"verified": False, "verifiedAt": "", "cookieCount": 0, "keepAlive": self.client.keepalive.status(False)},
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": ""},
            "logs": [], "results": [], "downloads": {"excel": False}, "totalFromServer": 0,
        }

    def _running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _log(self, level: str, message: str) -> None:
        self._state["logs"].append({"level": level, "message": message, "time": datetime.now().strftime("%H:%M:%S")})  # type: ignore[union-attr]

    def _event(self, event: dict[str, object]) -> None:
        with self._lock:
            if event.get("type") == "progress":
                self._state["progress"] = {key: event.get(key, "" if key == "current" else 0) for key in ("total", "completed", "success", "failed", "current")}
            elif event.get("type") == "record_result":
                self._state["results"].append({key: value for key, value in event.items() if key != "type"})  # type: ignore[union-attr]
            elif event.get("type") == "log":
                self._log(str(event.get("level", "info")), str(event.get("message", "")))

    def _start_keepalive(self) -> None:
        self.client.keepalive.record_success()
        self.client.keepalive.start(self.client.check_session, lambda error: isinstance(error, PortalSessionExpired), self._on_expired)

    def _on_expired(self) -> None:
        self.client.invalidate_credentials()
        with self._lock:
            self._stop_event.set()
            self._state["phase"] = "session_expired"
            self._state["message"] = "保活检查发现登录凭据已失效，已停止后续抓取"
            self._state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0}
            self._log("error", str(self._state["message"]))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            if isinstance(session, dict):
                session["keepAlive"] = self.client.keepalive.status(bool(session.get("verified")))
            state.update({"canVerify": not self._running(), "canRun": bool(session and session.get("verified")) and not self._running(), "canStop": self._running()})
            return state

    def verify_credentials(self, text: str) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("任务运行中，不能更换凭据")
            self._state["phase"], self._state["message"] = "verifying_credentials", "正在验证 CAAC 登录凭据"
        self.client.keepalive.stop()
        try:
            summary = self.client.load_credentials(text)
        except Exception as error:
            with self._lock:
                self._state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0}
                self._state["phase"], self._state["message"] = "waiting_credentials", str(error)
                self._log("error", str(error))
            raise
        with self._lock:
            self._state["session"] = {"verified": True, "verifiedAt": summary["verifiedAt"], "cookieCount": summary["cookieCount"]}
            self._state["totalFromServer"] = summary.get("total", 0)
            self._state["phase"], self._state["message"] = "credentials_ready", f"凭据有效，接口报告 {summary.get('total', 0)} 名有效飞行员"
            self._log("success", str(self._state["message"]))
            self._start_keepalive()
            state = self.snapshot()
            state["credentials"] = self.client.copyable_credentials
            return state

    def _worker(self, run_id: str) -> None:
        try:
            records, total = self.client.fetch_all_pilots()
            exporter = ResultExporter(self.app_directory / "results" / run_id, run_id)
            with self._lock:
                self._records = records
                self._path = exporter.path
                self._state["totalFromServer"] = total
                self._state["progress"] = {"total": total, "completed": 0, "success": 0, "failed": 0, "current": ""}
                self._log("info", f"列表分页完成：接口报告 {total} 名，实际获取 {len(records)} 名")
            result = BatchRunner(self.client, self._stop_event, self._event, exporter.append).run(records, total)
            path = exporter.finalize()
            with self._lock:
                self._path = path
                self._state["progress"] = {"total": total, "completed": len(result.outcomes), "success": result.success, "failed": result.failed, "current": ""}
                self._state["downloads"] = {"excel": True}
                if result.session_expired:
                    self._state["phase"], self._state["message"] = "session_expired", "登录凭据已失效，已保存已抓取结果"
                elif result.stopped:
                    self._state["phase"], self._state["message"] = "terminated", "任务已终止，已保存当前结果"
                else:
                    self._state["phase"], self._state["message"] = "completed", f"抓取完成：成功 {result.success}，失败 {result.failed}"
                self._log("success" if result.success else "warning", str(self._state["message"]))
        except PortalSessionExpired as error:
            with self._lock:
                self._state["phase"], self._state["message"] = "session_expired", str(error)
                self._log("error", str(error))
        except Exception as error:
            with self._lock:
                self._state["phase"], self._state["message"] = "failed", f"批次失败：{error}"
                self._log("error", str(self._state["message"]))

    def run(self) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("已有任务运行中")
            if not self._state["session"]["verified"]:  # type: ignore[index]
                raise RuntimeError("请先验证登录凭据")
            run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
            self._stop_event = threading.Event()
            self._path = None
            self._state.update({"phase": "running", "message": "开始动态获取有效飞行员列表", "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": "正在获取分页列表"}, "results": [], "downloads": {"excel": False}, "runId": run_id, "logs": []})
            self._thread = threading.Thread(target=self._worker, args=(run_id,), name="caac-pilot-export-runner", daemon=True)
            self._thread.start()
            return self.snapshot()

    def stop(self) -> dict[str, object]:
        with self._lock:
            self._stop_event.set()
            if not self._running():
                self._state["phase"], self._state["message"] = "terminated", "当前没有运行中的任务"
            else:
                self._state["phase"], self._state["message"] = "stopping", "正在停止后续请求"
            return self.snapshot()

    def download_path(self) -> Path | None:
        with self._lock:
            return self._path if self._path and self._path.is_file() else None

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.client.close()
