from __future__ import annotations

from datetime import date

from ieb_protocol.training_arrangement import TrainingArrangementProtocol
from ieb_protocol.training_arrangement_contract import display_window

from ...catalog import EndpointRecord
from .common import required, response_payload


def _date(value: object, label: str) -> date:
    if value is None or not str(value or "").strip():
        if label == "结束日期":
            return date.today()
    raw = required({"value": value}, "value", label)
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"{label}必须使用 YYYY-MM-DD") from error


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: TrainingArrangementProtocol,
) -> tuple[object, dict[str, object]]:
    if record.full_id == "training-arrangement.query-page":
        response, page = protocol.request_page(
            required(supplied, "trainItemArray", "训练类别"),
            _date(supplied.get("checkStartDt"), "开始日期"),
            _date(supplied.get("checkEndDt"), "结束日期"),
            int(supplied.get("page") or 1),
        )
        return response, {
            "summary": {"period": "自定义", "page": page.page, "recordCount": len(page.rows), "total": page.total},
            "tables": [{"id": "training-arrangement", "title": "训练安排", "columns": page.headers, "rows": page.rows}],
        }
    response, windows = protocol.request_periods(
        required(supplied, "trainItemArray", "训练类别"),
        _date(supplied.get("endDate"), "结束日期"),
        str(supplied.get("dateRange") or "all"),
    )
    return response, {
        "summary": {
            "category": str(supplied.get("trainItemArray") or ""),
            "periodCount": len(windows),
            "recordCount": sum(len(window.rows) for window in windows),
        },
        "tables": [
            {
                "id": f"training-arrangement-{window.key}",
                "title": f"{window.label}（{window.start.isoformat()} 至 {window.end.isoformat()}）",
                "columns": window.headers,
                "rows": window.rows,
            }
            for window in windows
        ],
    }
