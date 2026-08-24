"""OA 公文已阅逐条执行器。"""

from __future__ import annotations

import threading
from typing import Callable

from .models import BatchResult, WaitingRecord
from .portal_client import PortalSessionExpired


Event = dict[str, object]


class BatchRunner:
    def __init__(
        self,
        portal: object,
        stop_event: threading.Event | None = None,
        emit: Callable[[Event], None] | None = None,
    ) -> None:
        self.portal = portal
        self.stop_event = stop_event or threading.Event()
        self.emit = emit or (lambda _event: None)

    def run(self, records: list[WaitingRecord], limit: int) -> BatchResult:
        eligible = [record for record in records if record.eligible]
        skipped = len(records) - len(eligible)
        targets = eligible[:limit]
        success = 0
        failed = 0
        session_expired = False
        error_message = ""
        self._progress(len(targets), 0, 0, 0, "准备开始")

        for index, record in enumerate(targets, start=1):
            if self.stop_event.is_set():
                break
            self._progress(len(targets), index - 1, success, failed, record.title)
            stop_after_failure = False
            try:
                self.portal.mark_read(record)  # type: ignore[attr-defined]
                success += 1
                status = "成功"
                message = "已阅接口返回成功"
                level = "success"
            except PortalSessionExpired as error:
                failed += 1
                session_expired = True
                error_message = str(error)
                status = "失败"
                message = error_message
                level = "error"
                stop_after_failure = True
            except Exception as error:
                failed += 1
                status = "失败"
                message = str(error)
                level = "error"

            self.emit({"type": "record_result", **record.public_result(status, message)})
            self.emit(
                {
                    "type": "log",
                    "level": level,
                    "message": f"第 {index} 条《{record.title}》{status}",
                }
            )
            self._progress(len(targets), success + failed, success, failed, "")
            if stop_after_failure:
                break

        stopped = self.stop_event.is_set() and success + failed < len(targets)
        return BatchResult(
            success=success,
            failed=failed,
            skipped=skipped,
            stopped=stopped,
            session_expired=session_expired,
            error=error_message,
        )

    def _progress(self, total: int, completed: int, success: int, failed: int, current: str) -> None:
        self.emit(
            {
                "type": "progress",
                "total": total,
                "completed": completed,
                "success": success,
                "failed": failed,
                "current": current,
            }
        )
