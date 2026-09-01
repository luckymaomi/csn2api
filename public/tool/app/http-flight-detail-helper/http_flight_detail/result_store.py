from __future__ import annotations

import copy

from ieb_protocol.flight_detail_contract import DETAIL_HEADERS

from .models import Event


STATUS_COLUMNS = ["序号", "姓名", "员工号", "查询月份", "状态", "航班数量", "错误说明"]
DETAIL_COLUMNS = ["序号", "姓名", "员工号", *DETAIL_HEADERS[1:]]


class ResultStore:
    """维护页面结果缓存、版本和有限窗口分页。"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.version = 0
        self.status_rows: list[dict[str, object]] = []
        self.detail_rows: list[dict[str, object]] = []

    def add(self, event: Event) -> None:
        event_rows = event.get("rows") or []
        self.status_rows.append({
            "序号": len(self.status_rows) + 1,
            "姓名": event.get("name", ""),
            "员工号": event.get("employeeId", ""),
            "查询月份": event.get("month", ""),
            "状态": event.get("status", ""),
            "航班数量": len(event_rows) if isinstance(event_rows, list) else 0,
            "错误说明": event.get("error", ""),
        })
        for row in event_rows:
            if isinstance(row, dict):
                self.detail_rows.append({
                    "序号": len(self.detail_rows) + 1,
                    "姓名": str(event.get("name", "")),
                    "员工号": str(event.get("employeeId", "")),
                    **{header: str(row.get(header, "") or "") for header in DETAIL_HEADERS[1:]},
                })
        self.version += 1

    def metadata(self) -> dict[str, int]:
        return {"statusTotal": len(self.status_rows), "detailTotal": len(self.detail_rows), "version": self.version}

    def page(self, kind: str, offset: int, limit: int) -> dict[str, object]:
        if kind not in {"status", "detail"}:
            raise ValueError("结果类型必须是 status 或 detail")
        try:
            safe_offset = max(0, int(offset))
            safe_limit = max(1, min(200, int(limit)))
        except (TypeError, ValueError) as error:
            raise ValueError("分页参数无效") from error
        source = self.status_rows if kind == "status" else self.detail_rows
        columns = STATUS_COLUMNS if kind == "status" else DETAIL_COLUMNS
        return {
            "kind": kind,
            "columns": columns,
            "rows": copy.deepcopy(source[safe_offset:safe_offset + safe_limit]),
            "offset": safe_offset,
            "limit": safe_limit,
            "total": len(source),
            "version": self.version,
        }
