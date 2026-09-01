from __future__ import annotations

import threading
from typing import Callable

from ieb_protocol.flight_detail_contract import DETAIL_HEADERS

from .models import BatchResult, Event, MonthOutcome, QueryRecord
from .portal_client import PortalSessionExpired


class BatchRunner:
    def __init__(self, portal: object, stop_event: threading.Event | None = None, emit: Callable[[Event], None] | None = None, checkpoint: Callable[[list[MonthOutcome]], None] | None = None) -> None:
        self.portal = portal
        self.stop_event = stop_event or threading.Event()
        self.emit = emit or (lambda _event: None)
        self.checkpoint = checkpoint or (lambda _outcomes: None)

    def run(self, records: list[QueryRecord]) -> BatchResult:
        jobs = [(record_index, record, month) for record_index, record in enumerate(records) for month in record.months()]
        outcomes: list[MonthOutcome] = []
        session_expired = False
        timelines: dict[int, list[dict[str, str]]] = {}
        timeline_errors: dict[int, str] = {}
        self.emit({"type": "progress", "total": len(jobs), "completed": 0, "success": 0, "failed": 0, "current": ""})
        for index, (record_index, record, month) in enumerate(jobs):
            if self.stop_event.is_set() or session_expired:
                break
            status = "成功"
            rows = None
            headers = None
            error = ""
            try:
                if record_index in timeline_errors:
                    raise RuntimeError(timeline_errors[record_index])
                if record_index not in timelines:
                    try:
                        timelines[record_index] = self.portal.load_timeline(record)  # type: ignore[attr-defined]
                    except PortalSessionExpired:
                        raise
                    except Exception as exc:  # noqa: BLE001 - 同一人员不重复请求失败的时间轴
                        timeline_errors[record_index] = str(exc)
                        raise
                timeline = timelines[record_index]
                headers, rows = self.portal.query_month(record, month, timeline)  # type: ignore[attr-defined]
                if headers != DETAIL_HEADERS:
                    raise ValueError("航班明细表头不符合真实契约")
            except PortalSessionExpired as exc:
                status, error, session_expired = "失败", str(exc), True
            except Exception as exc:  # noqa: BLE001 - 行级错误必须继续
                status, error = "失败", str(exc)
            outcome = MonthOutcome(index, record_index, record, month, status, rows, headers, error)
            outcomes.append(outcome)
            self.emit({
                "type": "month_result", "index": index, "recordIndex": record_index,
                "employeeId": record.employee_id, "name": record.name, "month": month,
                "status": status, "headers": headers or [], "rows": rows or [], "error": error,
            })
            self.checkpoint(list(outcomes))
            success = sum(item.status == "成功" for item in outcomes)
            self.emit({"type": "progress", "total": len(jobs), "completed": len(outcomes), "success": success, "failed": len(outcomes) - success, "current": "" if len(outcomes) == len(jobs) else f"{record.name} {month}"})
        for index, (record_index, record, month) in enumerate(jobs[len(outcomes):], start=len(outcomes)):
            reason = "未查询：已终止" if self.stop_event.is_set() else "未查询：登录凭据已失效"
            outcomes.append(MonthOutcome(index, record_index, record, month, "未查询", error=reason))
            self.emit({"type": "month_result", "index": index, "recordIndex": record_index, "employeeId": record.employee_id, "name": record.name, "month": month, "status": "未查询", "headers": [], "rows": [], "error": reason})
            self.checkpoint(list(outcomes))
        return BatchResult(outcomes, self.stop_event.is_set(), session_expired)
