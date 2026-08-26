from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .exporter import BASE_HEADERS, ResultExporter, build_export_row
from .input_data import read_input
from .models import InputIssue, InputPayload, PilotOutcome, PilotRecord
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
        self._preview_headers = list(BASE_HEADERS)
        self._preview_rows: list[dict[str, str]] = []
        self._preview_version = 0
        self._state: dict[str, object] = {
            "phase": "waiting_credentials",
            "message": "等待验证登录凭据",
            "mode": "all",
            "session": {
                "verified": False,
                "verifiedAt": "",
                "cookieCount": 0,
                "identity": None,
                "keepAlive": self.client.keepalive.status(False),
            },
            "checks": {"data": {"checked": False, "ok": False, "validCount": 0, "invalidCount": 0, "errors": []}},
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "current": ""},
            "logs": [],
            "results": [],
            "resultTable": {"total": 0, "version": 0},
            "downloads": {"excel": False},
            "totalFromServer": 0,
        }

    def _running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _log(self, level: str, message: str) -> None:
        self._state["logs"].append({"level": level, "message": message, "time": datetime.now().strftime("%H:%M:%S")})  # type: ignore[union-attr]

    def _set_unverified(self) -> None:
        self._state["session"] = {"verified": False, "verifiedAt": "", "cookieCount": 0, "identity": None}

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
            self._set_unverified()
            self._log("error", str(self._state["message"]))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            if isinstance(session, dict):
                session["keepAlive"] = self.client.keepalive.status(bool(session.get("verified")))
            verified = bool(session and session.get("verified"))
            state.update({
                "canVerify": not self._running(),
                "canCheckData": verified and not self._running(),
                "canRun": verified and not self._running(),
                "canStop": self._running(),
            })
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
                self._set_unverified()
                self._state["phase"], self._state["message"] = "waiting_credentials", str(error)
                self._log("error", str(error))
            raise
        with self._lock:
            self._state["session"] = {
                "verified": True,
                "verifiedAt": summary["verifiedAt"],
                "cookieCount": summary["cookieCount"],
                "identity": None,
            }
            self._state["totalFromServer"] = summary.get("total", 0)
            self._state["phase"], self._state["message"] = "credentials_ready", f"凭据有效，接口报告 {summary.get('total', 0)} 名飞行员"
            self._log("success", str(self._state["message"]))
            self._start_keepalive()
            state = self.snapshot()
            state["credentials"] = self.client.copyable_credentials
            return state

    @staticmethod
    def _selected_records(payload: InputPayload) -> tuple[list[PilotRecord], list[InputIssue]]:
        valid_records, issues = read_input(payload)
        if not valid_records and issues and all(issue.input_row <= 1 for issue in issues):
            raise ValueError(str(issues[0]))
        ordered: list[tuple[int, PilotRecord | InputIssue]] = [
            *((record.input_row, record) for record in valid_records),
            *((issue.input_row, issue) for issue in issues),
        ]
        prepared: list[PilotRecord] = []
        for index, (_row, item) in enumerate(sorted(ordered, key=lambda pair: pair[0])):
            if isinstance(item, PilotRecord):
                prepared.append(PilotRecord(index, {}, item.input_name, item.input_archive_no, item.source, "", item.input_row))
            else:
                prepared.append(PilotRecord(index, {}, item.name, item.archive_no, item.source, item.message, item.input_row))
        return prepared, issues

    def check_data(self, mode: str, payload: InputPayload | None = None) -> dict[str, object]:
        if mode not in {"all", "selected"}:
            raise ValueError("抓取模式无效")
        with self._lock:
            if self._running():
                raise RuntimeError("任务运行中，不能检查另一批数据")
            if not self._state["session"]["verified"]:  # type: ignore[index]
                raise RuntimeError("请先验证登录凭据")
        if mode == "all":
            valid_count = int(self._state.get("totalFromServer", 0) or 0)
            issues: list[InputIssue] = []
        else:
            records, issues = self._selected_records(payload or InputPayload())
            valid_count = sum(not record.input_error for record in records)
        errors = [str(issue) for issue in issues]
        with self._lock:
            self._state["mode"] = mode
            self._state["checks"] = {"data": {"checked": True, "ok": valid_count > 0, "validCount": valid_count, "invalidCount": len(issues), "errors": errors}}
            self._state["phase"] = "data_checked"
            self._state["message"] = f"名单检查完成：有效 {valid_count} 条，无效 {len(issues)} 条" if mode == "selected" else f"全量抓取已就绪：当前接口报告 {valid_count} 人"
            self._log("success" if valid_count else "warning", str(self._state["message"]))
            return self.snapshot()

    def _persist(self, exporter: ResultExporter, outcome: PilotOutcome) -> None:
        exporter.append(outcome)
        row = build_export_row(outcome)
        with self._lock:
            for header in row:
                if header not in self._preview_headers:
                    self._preview_headers.append(header)
            self._preview_rows.append(row)
            self._preview_version += 1
            self._state["resultTable"] = {"total": len(self._preview_rows), "version": self._preview_version}

    def _worker(self, run_id: str, mode: str, selected_records: list[PilotRecord] | None) -> None:
        exporter = ResultExporter(self.app_directory / "results" / run_id, run_id)
        try:
            if mode == "all":
                records, total = self.client.fetch_all_pilots()
                list_message = f"列表分页完成：接口报告 {total} 名，实际获取 {len(records)} 名"
            else:
                records = selected_records or []
                total = len(records)
                list_message = f"名单读取完成：本次处理 {total} 条"
            with self._lock:
                self._path = exporter.path
                self._state["progress"] = {"total": total, "completed": 0, "success": 0, "failed": 0, "current": ""}
                self._log("info", list_message)
            result = BatchRunner(self.client, self._stop_event, self._event, lambda outcome: self._persist(exporter, outcome)).run(records, total)
            path = exporter.finalize()
            with self._lock:
                self._path = path
                self._state["progress"] = {"total": total, "completed": len(result.outcomes), "success": result.success, "failed": result.failed, "current": ""}
                self._state["downloads"] = {"excel": True}
                if result.session_expired:
                    self.client.invalidate_credentials()
                    self._set_unverified()
                    self._state["phase"], self._state["message"] = "session_expired", "登录凭据已失效，已保存当前结果"
                elif result.stopped:
                    self._state["phase"], self._state["message"] = "terminated", "任务已终止，已保存当前结果"
                else:
                    self._state["phase"], self._state["message"] = "completed", f"抓取完成：成功 {result.success}，失败 {result.failed}"
                self._log("success" if result.success else "warning", str(self._state["message"]))
        except PortalSessionExpired as error:
            with self._lock:
                self.client.invalidate_credentials()
                self._set_unverified()
                self._state["phase"], self._state["message"] = "session_expired", str(error)
                self._log("error", str(error))
        except Exception as error:
            with self._lock:
                self._state["phase"], self._state["message"] = "failed", f"批次失败：{error}"
                self._log("error", str(self._state["message"]))

    def run(self, mode: str = "all", payload: InputPayload | None = None) -> dict[str, object]:
        if mode not in {"all", "selected"}:
            raise ValueError("抓取模式无效")
        with self._lock:
            if self._running():
                raise RuntimeError("已有任务运行中")
            if not self._state["session"]["verified"]:  # type: ignore[index]
                raise RuntimeError("请先验证登录凭据")
        selected_records: list[PilotRecord] | None = None
        issues: list[InputIssue] = []
        if mode == "selected":
            selected_records, issues = self._selected_records(payload or InputPayload())
            if not selected_records:
                raise ValueError("名单中没有可处理的人员")
        run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._stop_event = threading.Event()
            self._path = None
            self._preview_headers = list(BASE_HEADERS)
            self._preview_rows = []
            self._preview_version = 0
            total = len(selected_records or []) if mode == "selected" else 0
            self._state.update({
                "phase": "running",
                "message": f"开始处理名单中的 {total} 条记录" if mode == "selected" else "开始动态获取飞行员列表",
                "mode": mode,
                "progress": {"total": total, "completed": 0, "success": 0, "failed": 0, "current": "正在准备人员列表"},
                "results": [],
                "resultTable": {"total": 0, "version": 0},
                "downloads": {"excel": False},
                "runId": run_id,
                "logs": [],
                "checks": {"data": {"checked": mode == "selected", "ok": True, "validCount": total - len(issues), "invalidCount": len(issues), "errors": [str(issue) for issue in issues]}},
            })
            self._log("info", str(self._state["message"]))
            for issue in issues:
                self._log("warning", str(issue))
            self._thread = threading.Thread(target=self._worker, args=(run_id, mode, selected_records), name="caac-pilot-export-runner", daemon=True)
            self._thread.start()
            return self.snapshot()

    def results_page(self, offset: int = 0, limit: int = 50) -> dict[str, object]:
        safe_offset = max(0, int(offset))
        safe_limit = max(1, min(200, int(limit)))
        with self._lock:
            return {
                "columns": list(self._preview_headers),
                "rows": copy.deepcopy(self._preview_rows[safe_offset:safe_offset + safe_limit]),
                "offset": safe_offset,
                "limit": safe_limit,
                "total": len(self._preview_rows),
                "version": self._preview_version,
            }

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
            self._thread.join(timeout=35)
        self.client.close()
