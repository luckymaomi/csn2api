from __future__ import annotations

import threading
from typing import Callable

from .models import BatchResult, PilotOutcome, PilotRecord
from .portal_client import PortalSessionExpired


class BatchRunner:
    def __init__(self, portal: object, stop_event: threading.Event | None = None, emit: Callable[[dict[str, object]], None] | None = None, persist: Callable[[PilotOutcome], None] | None = None) -> None:
        self.portal = portal
        self.stop_event = stop_event or threading.Event()
        self.emit = emit or (lambda _event: None)
        self.persist = persist or (lambda _outcome: None)

    def run(self, records: list[PilotRecord], total: int) -> BatchResult:
        outcomes: list[PilotOutcome] = []
        session_expired = False
        for record in records:
            if self.stop_event.is_set() or session_expired:
                break
            self.emit({"type": "progress", "total": total, "completed": len(outcomes), "success": sum(item.status == "成功" for item in outcomes), "failed": sum(item.status != "成功" for item in outcomes), "current": f"{record.name or record.pilot_id}（{record.pilot_id}）"})
            try:
                outcome = self.portal.query_one(record)  # type: ignore[attr-defined]
            except PortalSessionExpired as error:
                session_expired = True
                outcome = PilotOutcome(record, "失败", error=str(error))
            except Exception as error:
                outcome = PilotOutcome(record, "失败", error=f"{error.__class__.__name__}: {error}")
            self.persist(outcome)
            outcomes.append(outcome)
            self.emit({"type": "record_result", "index": record.index, "pilotId": record.pilot_id, "name": record.name, "status": outcome.status, "error": outcome.error})
            self.emit({"type": "log", "level": "success" if outcome.status == "成功" else "error", "message": f"{record.name or record.pilot_id}：{outcome.status}{('，' + outcome.error) if outcome.error else ''}"})
        stopped = self.stop_event.is_set()
        if stopped or session_expired:
            reason = "用户终止" if stopped else "登录凭据已失效，未继续抓取"
            status = "已终止" if stopped else "未查询"
            for record in records[len(outcomes):]:
                outcome = PilotOutcome(record, status, error=reason)
                self.persist(outcome)
                outcomes.append(outcome)
                self.emit({"type": "record_result", "index": record.index, "pilotId": record.pilot_id, "name": record.name, "status": status, "error": reason})
        return BatchResult(outcomes, total, stopped, session_expired)
