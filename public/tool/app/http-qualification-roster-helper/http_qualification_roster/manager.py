from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exporter import RosterWorkbook
from ieb_protocol.roster_models import OperatingQualification, QueryFilters, qualifications_from_payload
from .portal_client import PortalClient, PortalSessionExpired
from .runner import RosterRunner, RunSummary
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
        if client is not None and hasattr(self.client, "keepalive"):
            self.client.keepalive.interval_factory = keepalive_interval_factory
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._qualifications: list[OperatingQualification] = []
        self._filter_fields: list[dict[str, object]] = []
        self._download: Path | None = None
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, object]:
        return {
            "phase": "waiting_credentials",
            "session": {
                "verified": False,
                "verifiedAt": "",
                "identity": None,
                "keepAlive": self.client.keepalive.status(False),
            },
            "metadata": {"loaded": False, "loadedAt": ""},
            "filterFields": [],
            "qualifications": [],
            "items": [],
            "resultColumns": [],
            "results": [],
            "progress": {"total": 0, "completed": 0, "success": 0, "failed": 0, "relationships": 0},
            "current": None,
            "download": {"ready": False, "name": ""},
            "logs": [],
            "error": "",
        }

    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _log(self, level: str, message: str) -> None:
        logs = self._state["logs"]
        assert isinstance(logs, list)
        logs.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "message": SECRET_PATTERN.sub(r"\1=[已隐藏]", message),
        })
        del logs[:-200]

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            state = copy.deepcopy(self._state)
            session = state.get("session")
            if isinstance(session, dict):
                session["keepAlive"] = self.client.keepalive.status(bool(session.get("verified")))
            return state

    def _start_keepalive(self) -> None:
        self.client.keepalive.record_success()
        self.client.keepalive.start(
            self.client.check_session,
            lambda error: isinstance(error, PortalSessionExpired),
            self._handle_keepalive_expired,
        )

    def _handle_keepalive_expired(self) -> None:
        self.client.invalidate_credentials()
        with self._lock:
            self._stop_event.set()
            session = self._state["session"]
            assert isinstance(session, dict)
            session.update({"verified": False, "identity": None})
            self._state["phase"] = "session_expired"
            self._state["error"] = "保活检查发现登录凭据已失效，已停止后续查询"
            self._log("error", str(self._state["error"]))

    def verify_credentials(self, source: str) -> dict[str, object]:
        with self._lock:
            if self._running():
                raise RuntimeError("查询任务进行中，不能重新验证凭据")
            self._state["phase"] = "verifying"
            self._state["error"] = ""
        self.client.keepalive.stop()
        try:
            summary = self.client.load_credentials(source)
        except Exception as error:
            with self._lock:
                self._state = self._initial_state()
                self._state["error"] = _safe_error(error)
                self._log("error", "登录凭据验证失败")
            raise
        with self._lock:
            self._qualifications = []
            self._filter_fields = []
            self._state = self._initial_state()
            self._state["phase"] = "ready"
            self._state["session"] = {
                "verified": True,
                "verifiedAt": summary["verifiedAt"],
                "identity": summary["identity"],
            }
            self._start_keepalive()
            self._log("success", "飞行门户 Cookie 验证成功")
            state = self.snapshot()
            state["credentials"] = self.client.copyable_credentials
            return state

    def load_metadata(self) -> dict[str, object]:
        with self._lock:
            self.client.require_credentials()
            if self._running():
                raise RuntimeError("查询任务进行中，不能重新加载筛选")
            self._state["phase"] = "loading_metadata"
            self._state["error"] = ""
        try:
            fields, qualifications = self.client.load_metadata()
        except PortalSessionExpired as error:
            self.client.clear_credentials()
            with self._lock:
                session = self._state["session"]
                assert isinstance(session, dict)
                session.update({"verified": False, "identity": None})
                self._state["phase"] = "session_expired"
                self._state["error"] = _safe_error(error)
                self._log("error", "加载筛选时发现登录会话已失效")
            raise
        except Exception as error:
            with self._lock:
                self._state["phase"] = "ready"
                self._state["error"] = _safe_error(error)
                self._log("error", "门户筛选加载失败")
            raise
        with self._lock:
            self._qualifications = list(qualifications)
            self._filter_fields = [field.to_dict() for field in fields]
            self._state["metadata"] = {
                "loaded": True,
                "loadedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._state["filterFields"] = self._filter_fields
            self._state["qualifications"] = [item.to_dict() for item in self._qualifications]
            self._state["phase"] = "ready"
            self._log("success", f"已加载 {len(fields)} 个筛选字段和 {len(qualifications)} 个运行资格")
            return self.snapshot()

    def _allowed_values(self, field_name: str) -> set[str]:
        field = next((item for item in self._filter_fields if item.get("name") == field_name), None)
        if not isinstance(field, dict):
            return set()
        return {str(option.get("value", "")) for option in field.get("options", []) if isinstance(option, dict)}

    def _validate_filters(self, filters: QueryFilters) -> None:
        values = {
            "primaryBaseArray": [filters.primary_base],
            "baseArray": [filters.operating_base],
            "techBase": [filters.technical_base],
            "fleetCdToArray": filters.fleet_codes,
            "bolMultiQualCd": [filters.multi_qualification],
            "qualTypeArray": filters.technical_levels,
            "bolPriBase": [filters.help_flying],
            "bolJCY": [filters.instructor_checker],
            "activeStatusArray": filters.active_statuses,
            "fleetCdbranch": [filters.branch],
        }
        for name, selected in values.items():
            allowed = self._allowed_values(name)
            if any(value and value not in allowed for value in selected):
                raise ValueError(f"筛选项 {name} 包含门户当前不存在的值")

    def start_query(self, payload: dict[str, object]) -> dict[str, object]:
        with self._lock:
            self.client.require_credentials()
            if self._running():
                raise RuntimeError("已有查询任务正在执行")
            if self._state.get("phase") == "loading_metadata":
                raise RuntimeError("门户筛选正在加载")
            metadata = self._state.get("metadata")
            if not isinstance(metadata, dict) or not metadata.get("loaded"):
                raise RuntimeError("请先加载门户筛选")
            filters = QueryFilters.from_payload(payload.get("filters"))
            self._validate_filters(filters)
            codes = qualifications_from_payload(payload.get("qualificationCodes"))
            selected = [item for item in self._qualifications if item.code in codes]
            if len(selected) != len(codes) or not selected:
                raise ValueError("请选择门户当前存在的运行资格")
            order = {code: index for index, code in enumerate(codes)}
            selected.sort(key=lambda item: order[item.code])
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
            target = self.output_directory / run_id / "运行资质人员名册.xlsx"
            workbook = RosterWorkbook(target)
            self._download = target.resolve()
            self._state["items"] = [
                {"code": item.code, "name": item.name, "status": "pending", "count": None, "error": ""}
                for item in selected
            ]
            self._state["resultColumns"] = []
            self._state["results"] = []
            self._state["progress"] = {
                "total": len(selected), "completed": 0, "success": 0, "failed": 0,
                "relationships": 0,
            }
            self._state["current"] = None
            self._state["download"] = {"ready": False, "name": target.name}
            self._state["phase"] = "querying"
            self._state["error"] = ""
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                args=(filters, selected, workbook),
                name="http-qualification-roster-runner",
                daemon=True,
            )
            self._thread.start()
            return self.snapshot()

    def _worker(self, filters: QueryFilters, selected: list[OperatingQualification], workbook: RosterWorkbook) -> None:
        try:
            summary = RosterRunner(self.client, workbook, self._handle_event, self._stop_event.is_set).run(filters, selected)
            self._finish(summary)
        except Exception as error:
            with self._lock:
                self._state["phase"] = "failed"
                self._state["error"] = _safe_error(error)
                self._state["current"] = None
                self._log("error", "查询任务异常结束")

    def _item(self, code: str) -> dict[str, object] | None:
        items = self._state["items"]
        assert isinstance(items, list)
        return next((item for item in items if item.get("code") == code), None)

    def _handle_event(self, event: dict[str, object]) -> None:
        with self._lock:
            code = str(event.get("code", ""))
            item = self._item(code)
            if item is None:
                return
            event_type = event.get("type")
            if event_type == "item_started":
                item["status"] = "running"
                self._state["current"] = {"code": code, "name": item["name"]}
                self._log("info", f"正在查询 {code}")
                return
            progress = self._state["progress"]
            assert isinstance(progress, dict)
            progress["completed"] = int(progress["completed"]) + 1
            if event_type == "item_succeeded":
                count = int(event.get("count", 0))
                item.update({"status": "success", "count": count})
                progress["success"] = int(progress["success"]) + 1
                columns = [str(value) for value in event.get("columns", []) if str(value)]
                result_columns = self._state["resultColumns"]
                assert isinstance(result_columns, list)
                if not result_columns:
                    result_columns.extend(columns)
                results = self._state["results"]
                assert isinstance(results, list)
                for raw in event.get("relations", []):
                    if not isinstance(raw, dict):
                        continue
                    results.append({
                        "sequence": len(results) + 1,
                        "fields": {column: raw.get(column, "") for column in result_columns},
                        "qualificationCode": code,
                    })
                progress["relationships"] = len(results)
                self._state["download"] = {"ready": True, "name": self._download.name if self._download else ""}
                self._log("success", f"{code} 已返回 {count} 人")
            elif event_type == "item_failed":
                item.update({"status": "failed", "error": str(event.get("error", "查询失败"))})
                progress["failed"] = int(progress["failed"]) + 1
                self._log("error", f"{code} 查询失败，继续后续资格")

    def _finish(self, summary: RunSummary) -> None:
        with self._lock:
            self._state["current"] = None
            if summary.session_expired:
                self.client.clear_credentials()
                session = self._state["session"]
                assert isinstance(session, dict)
                session.update({"verified": False, "identity": None})
                self._state["phase"] = "session_expired"
                self._log("error", "登录会话已失效，任务已停止")
            elif summary.interrupted:
                self._state["phase"] = "stopped"
                self._log("info", "任务已在当前请求返回后停止")
            elif summary.failed:
                self._state["phase"] = "partial_failure"
                self._log("error", "查询完成，部分资格失败")
            else:
                self._state["phase"] = "completed"
                self._log("success", "运行资质人员名册已生成")

    def stop(self) -> dict[str, object]:
        with self._lock:
            if not self._running():
                return self.snapshot()
            self._stop_event.set()
            self._state["phase"] = "stopping"
            self._log("info", "已请求停止，将在当前资格返回后生效")
            return self.snapshot()

    def download_path(self) -> Path | None:
        with self._lock:
            return self._download if self._download is not None and self._download.is_file() else None

    def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        self.client.keepalive.stop()
        self.client.close()
