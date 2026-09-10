from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .exporter import ResultExporter
from .area_defaults import area_details, resolve_area_defaults
from .models import Event, QueryInput
from .portal_client import PortalClient, PortalSessionExpired
from .runner import AreaDefaultRunner, QueryRunner
from .session_keepalive import random_keepalive_interval


SECRET_PATTERN = re.compile(r"(?i)(JSESSIONID|iebJSid)\s*=\s*[^;\s]+")


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
        if client is not None and hasattr(client, "keepalive"):
            client.keepalive.interval_factory = keepalive_interval_factory
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._downloads: dict[str, Path] = {}
        self._area_categories = []
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        return {
            "phase": "waiting_credentials",
            "message": "等待验证登录凭据",
            "session": {"verified": False, "verifiedAt": "", "identity": None, "cookieCount": 0},
            "metadata": {"loaded": False, "options": []},
            "areaDefaults": {"available": False, "categories": [], "error": ""},
            "selection": {"category": "", "dateRange": "all", "endDate": ""},
            "progress": {"period": "", "page": 0, "pages": 0, "records": 0},
            "results": [],
            "summary": [],
            "downloads": {"excel": False},
            "logs": [],
        }

    def _running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _append_log(self, level: str, message: str) -> None:
        logs = self._state["logs"]
        assert isinstance(logs, list)
        logs.append({"level": level, "message": SECRET_PATTERN.sub(r"\1=[已隐藏]", message), "time": datetime.now().strftime("%H:%M:%S")})
        del logs[:-100]

    def _start_keepalive(self) -> None:
        keepalive = getattr(self.client, "keepalive", None)
        check = getattr(self.client, "check_session", None)
        if keepalive is None or not callable(check):
            return
        keepalive.record_success()
        keepalive.start(check, lambda error: isinstance(error, PortalSessionExpired), self._handle_keepalive_expired)

    def _handle_keepalive_expired(self) -> None:
        self.client.invalidate_credentials()
        with self._lock:
            self._stop_event.set()
            session = self._state["session"]
            assert isinstance(session, dict)
            session.update({"verified": False, "identity": None, "cookieCount": 0})
            self._state["phase"] = "session_expired"
            self._state["message"] = "保活检查发现登录凭据已失效"
            self._append_log("error", str(self._state["message"]))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            keepalive = getattr(self.client, "keepalive", None)
            session = state.get("session")
            if isinstance(session, dict) and keepalive is not None:
                session["keepAlive"] = keepalive.status(bool(session.get("verified")))
            verified = isinstance(session, dict) and session.get("verified") is True
            state.update({
                "canVerify": not self._running(),
                "canLoadMetadata": verified and not self._running(),
                "canRun": verified and bool(state.get("metadata", {}).get("loaded")) and not self._running(),  # type: ignore[union-attr]
                "canRunArea": verified and bool(state.get("areaDefaults", {}).get("available")) and not self._running(),  # type: ignore[union-attr]
                "canStop": self._running(),
            })
            return state

    def verify_credentials(self, source: str) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("查询运行中，不能更换登录凭据")
            self._state["phase"] = "verifying_credentials"
            self._state["message"] = "正在验证登录凭据"
        self._stop_keepalive()
        try:
            summary = self.client.load_credentials(source)
        except Exception as error:
            self.client.clear_credentials()
            with self._lock:
                self._state = self._initial_state()
                self._state["message"] = _safe_error(error)
                self._append_log("error", "登录凭据验证失败")
            raise
        with self._lock:
            self._state["session"] = {"verified": True, **summary}
            self._state["phase"] = "credentials_ready"
            self._state["message"] = "登录凭据有效，请加载训练类别"
            self._start_keepalive()
            self._append_log("success", "凭据验证成功，纯 HTTP 查询接口已就绪")
            state = self.snapshot()
            credentials = str(getattr(self.client, "copyable_credentials", "") or "")
            if credentials:
                state["credentials"] = credentials
            return state

    def load_metadata(self) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("查询运行中，不能刷新训练类别")
            self.client.require_credentials()
        options = self.client.load_options()
        area_error = ""
        try:
            self._area_categories = resolve_area_defaults(options)
        except ValueError as error:
            self._area_categories = []
            area_error = str(error)
        with self._lock:
            self._state["metadata"] = {"loaded": True, "options": [{"value": item.value, "label": item.label} for item in options]}
            self._state["areaDefaults"] = {
                "available": not area_error,
                "error": area_error,
                "categories": [
                    {"name": category.name, "subjects": [item.label for item in category.subjects]}
                    for category in self._area_categories
                ],
            }
            self._state["phase"] = "ready"
            self._state["message"] = f"已加载 {len(options)} 个训练类别"
            self._append_log("success", str(self._state["message"]))
            return self.snapshot()

    @staticmethod
    def _end_date(payload: dict[str, object]) -> date:
        raw_end = str(payload.get("endDate", "") or "").strip()
        try:
            return date.fromisoformat(raw_end) if raw_end else date.today()
        except ValueError as error:
            raise ValueError("结束日期必须使用 YYYY-MM-DD") from error

    def _parse_input(self, payload: dict[str, object]) -> QueryInput:
        category = str(payload.get("category", "") or "").strip()
        date_range = str(payload.get("dateRange", "all") or "all").strip().lower()
        raw_end = str(payload.get("endDate", "") or "").strip()
        end_date = date.fromisoformat(raw_end) if raw_end else date.today()
        if not category:
            raise ValueError("请选择训练类别")
        if date_range not in {"all", "week", "month", "year"}:
            raise ValueError("时间范围不受支持")
        values = self._state["metadata"]["options"]  # type: ignore[index]
        if not any(isinstance(item, dict) and item.get("value") == category for item in values):
            raise ValueError("训练类别不是当前门户动态选项")
        return QueryInput(category, date_range, end_date)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("已有查询正在执行")
            self.client.require_credentials()
            if not self._state["metadata"]["loaded"]:  # type: ignore[index]
                raise RuntimeError("请先加载训练类别")
            mode = str(payload.get("mode", "single") or "single").strip().lower()
            if mode == "area-default":
                if not self._area_categories:
                    error = self._state.get("areaDefaults", {}).get("error", "")  # type: ignore[union-attr]
                    raise RuntimeError(str(error or "区域默认配置不可用"))
                end_date = self._end_date(payload)
                run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
                self._stop_event = threading.Event()
                self._downloads = {}
                self._state.update({
                    "phase": "running",
                    "message": "正在按区域默认配置串行查询周、月、年数据",
                    "selection": {"mode": "area-default", "dateRange": "all", "endDate": end_date.isoformat()},
                    "progress": {
                        "category": "", "subject": "", "period": "", "page": 0, "pages": 0, "records": 0,
                        "completedSubjects": 0,
                        "totalSubjects": sum(len(category.subjects) for category in self._area_categories),
                    },
                    "results": [],
                    "summary": [],
                    "downloads": {"excel": False},
                    "runId": run_id,
                    "logs": [],
                })
                self._append_log("info", str(self._state["message"]))
                self._thread = threading.Thread(
                    target=self._worker_area,
                    args=(end_date, run_id),
                    name="training-arrangement-area-runner",
                    daemon=True,
                )
                self._thread.start()
                return self.snapshot()
            query_input = self._parse_input(payload)
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            self._stop_event = threading.Event()
            self._downloads = {}
            self._state.update({
                "phase": "running",
                "message": "正在按周期串行查询全部分页",
                "selection": {"category": query_input.category, "dateRange": query_input.date_range, "endDate": query_input.end_date.isoformat()},
                "progress": {"period": "", "page": 0, "pages": 0, "records": 0},
                "results": [],
                "summary": [],
                "downloads": {"excel": False},
                "runId": run_id,
                "logs": [],
            })
            self._append_log("info", str(self._state["message"]))
            self._thread = threading.Thread(target=self._worker, args=(query_input, run_id), name="training-arrangement-runner", daemon=True)
            self._thread.start()
            return self.snapshot()

    def _handle_event(self, event: Event) -> None:
        with self._lock:
            if event.get("type") == "area_subject_started":
                progress = self._state["progress"]
                assert isinstance(progress, dict)
                progress.update({"category": event.get("category", ""), "subject": event.get("subject", ""), "period": "", "page": 0, "pages": 0, "records": 0})
                self._append_log("info", f"开始查询{event.get('category', '')}：{event.get('subject', '')}")
            elif event.get("type") == "area_subject_completed":
                progress = self._state["progress"]
                assert isinstance(progress, dict)
                progress["completedSubjects"] = int(progress.get("completedSubjects", 0) or 0) + 1
                self._append_log("success", f"已完成{event.get('category', '')}：{event.get('subject', '')}")
            elif event.get("type") == "area_results_updated":
                windows = event.get("windows", [])
                if isinstance(windows, list):
                    self._state["results"] = self._display_area_windows(windows)
                summary = event.get("summary", [])
                if isinstance(summary, list):
                    self._state["summary"] = summary
            elif event.get("type") == "period_started":
                progress = self._state["progress"]
                assert isinstance(progress, dict)
                progress.update({"category": event.get("category", progress.get("category", "")), "subject": event.get("subject", progress.get("subject", "")), "period": event.get("label", ""), "page": 0, "pages": 0, "records": 0})
                self._append_log("info", f"开始查询{event.get('label', '')}：{event.get('start', '')} 至 {event.get('end', '')}")
            elif event.get("type") == "page_completed":
                progress = self._state["progress"]
                assert isinstance(progress, dict)
                progress["page"] = int(event.get("page", 0) or 0)
                progress["records"] = int(progress.get("records", 0) or 0) + int(event.get("rows", 0) or 0)
            elif event.get("type") in {"error", "log"}:
                self._append_log(str(event.get("level", "error")), str(event.get("message", "")))

    def _worker(self, query_input: QueryInput, run_id: str) -> None:
        try:
            runner = QueryRunner(self.client, self._stop_event, self._handle_event)
            result = runner.run(query_input)
            with self._lock:
                self._state["results"] = [
                    {
                        "key": window.key,
                        "label": window.label,
                        "startDate": window.start.isoformat(),
                        "endDate": window.end.isoformat(),
                        "pages": window.pages,
                        "total": window.total if window.total is not None else len(window.rows),
                        "headers": window.headers,
                        "rows": window.rows,
                    }
                    for window in result.windows
                ]
            if result.session_expired:
                with self._lock:
                    self._state["phase"] = "session_expired"
                    self._state["message"] = "登录凭据已失效，已停止后续查询"
                return
            if result.interrupted:
                with self._lock:
                    self._state["phase"] = "terminated"
                    self._state["message"] = "查询已停止，当前已完成周期仍可导出"
                return
            path = ResultExporter(self.output_directory / "results" / run_id, run_id).write(result.windows).excel
            with self._lock:
                download_id = uuid.uuid4().hex
                self._downloads[download_id] = path.resolve()
                self._state["downloads"] = {"excel": True, "excelId": download_id, "fileName": path.name}
                self._state["phase"] = "completed"
                self._state["message"] = f"查询完成：{sum(len(window.rows) for window in result.windows)} 条记录"
                self._append_log("success", str(self._state["message"]))
        except Exception as error:
            with self._lock:
                self._state["phase"] = "failed"
                self._state["message"] = _safe_error(error)
                self._append_log("error", "查询失败")

    @staticmethod
    def _display_area_windows(windows: list[object]) -> list[dict[str, object]]:
        headers, rows = area_details(windows)  # type: ignore[arg-type]
        if not windows:
            return []
        starts = [getattr(window, "start") for window in windows]
        ends = [getattr(window, "end") for window in windows]
        return [{
            "category": "区域默认配置",
            "key": "details",
            "label": "去重明细",
            "startDate": min(starts).isoformat(),
            "endDate": max(ends).isoformat(),
            "pages": sum(int(getattr(window, "pages", 0)) for window in windows),
            "total": len(rows),
            "headers": headers,
            "rows": rows,
        }]

    def _worker_area(self, end_date: date, run_id: str) -> None:
        try:
            runner = AreaDefaultRunner(self.client, self._stop_event, self._handle_event)
            result = runner.run(self._area_categories, end_date)
            with self._lock:
                self._state["results"] = self._display_area_windows(list(result.windows))
                self._state["summary"] = result.summary
            if result.session_expired:
                with self._lock:
                    self._state["phase"] = "session_expired"
                    self._state["message"] = "登录凭据已失效，已停止后续查询"
                return
            if result.interrupted:
                with self._lock:
                    self._state["phase"] = "terminated"
                    self._state["message"] = "查询已停止，当前已完成结果仍可导出"
                return
            path = ResultExporter(self.output_directory / "results" / run_id, run_id).write_area(result.windows, result.summary).excel
            with self._lock:
                download_id = uuid.uuid4().hex
                self._downloads[download_id] = path.resolve()
                self._state["downloads"] = {"excel": True, "excelId": download_id, "fileName": path.name}
                self._state["phase"] = "completed"
                self._state["message"] = f"区域默认导出完成：{sum(len(window.rows) for window in result.windows)} 条明细"
                self._append_log("success", str(self._state["message"]))
        except Exception as error:
            with self._lock:
                self._state["phase"] = "failed"
                self._state["message"] = _safe_error(error)
                self._append_log("error", f"区域默认查询失败：{self._state['message']}")

    def start(self, credentials: str, payload: dict[str, object]) -> dict[str, object]:
        self.verify_credentials(credentials)
        self.load_metadata()
        return self.run(payload)

    def stop(self) -> dict[str, object]:
        with self._lock:
            if self._running():
                self._stop_event.set()
                self._state["phase"] = "stopping"
                self._state["message"] = "已请求停止，将在当前请求完成后生效"
            return self.snapshot()

    def download_path(self, download_id: str) -> Path | None:
        with self._lock:
            path = self._downloads.get(str(download_id or ""))
            return path if path is not None and path.is_file() else None

    def _stop_keepalive(self) -> None:
        keepalive = getattr(self.client, "keepalive", None)
        if keepalive is not None:
            keepalive.stop()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._stop_keepalive()
        self.client.close()
