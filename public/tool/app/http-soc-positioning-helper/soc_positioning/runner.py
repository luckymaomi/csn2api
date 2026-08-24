"""Strictly serial SOC positioning runner."""

from __future__ import annotations

import threading
from typing import Callable

from .models import FlightOption
from .portal_client import PortalError, PortalSessionExpired, SocPortalClient
from .result_store import ResultStore


EventCallback = Callable[[dict[str, object]], None]


class BatchRunner:
    def __init__(self, client: SocPortalClient, store: ResultStore, stop_event: threading.Event, emit: EventCallback | None = None):
        self.client, self.store, self.stop_event = client, store, stop_event
        self.emit = emit or (lambda _event: None)

    def _result(self, record: dict[str, object], status: str, message: str = "", option: FlightOption | None = None, name: str = "") -> dict[str, object]:
        return {
            "type": "record_result", "来源行": record.get("来源行", ""), "员工号": record.get("员工号", ""),
            "姓名": name or record.get("姓名", ""), "航班日期": record.get("航班日期", ""),
            "出发地": record.get("出发地", ""), "目的地": record.get("目的地", ""),
            "航班号": option.display_number if option else record.get("航班号", ""),
            "申请原因": record.get("申请原因", ""), "备注": record.get("备注", ""), "状态": status, "说明": message,
        }

    def _emit_result(self, row: dict[str, object]) -> None:
        self.store.append(row)
        self.emit(row)

    def run(self, records: list[dict[str, object]]) -> dict[str, object]:
        summary: dict[str, object] = {"total": len(records), "completed": 0, "success": 0, "failed": 0, "stopped": False}
        self.emit({"type": "progress", **summary, "current": ""})
        for record in records:
            if self.stop_event.is_set():
                summary["stopped"] = True
                break
            self.emit({"type": "progress", **summary, "current": f"{record.get('员工号', '')} {record.get('姓名', '')}"})
            success = False
            try:
                options = self.client.list_flights(str(record["航班日期"]), str(record["出发地"]), str(record["目的地"]))
                option = self.client.choose_flight(options, str(record.get("航班号", "")))
                identity = self.client.validate_staff(record, option)
                outcome = self.client.submit(record, option, identity)
                if not outcome.success:
                    raise PortalError(outcome.message)
                self._emit_result(self._result(record, "成功", outcome.message, option, identity.name))
                success = True
            except PortalSessionExpired:
                raise
            except Exception as error:
                self._emit_result(self._result(record, "失败", str(error)))
                self.emit({"type": "log", "level": "warning", "message": f"第{record.get('来源行', '')}行已标记失败并继续：{error}"})
            summary["completed"] = int(summary["completed"]) + 1
            summary["success" if success else "failed"] = int(summary["success" if success else "failed"]) + 1
            self.emit({"type": "progress", **summary, "current": ""})
        return summary
