from __future__ import annotations

from ieb_protocol.flight_detail import FlightDetailProtocol

from ...catalog import EndpointRecord
from .common import required


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: FlightDetailProtocol,
) -> tuple[object, dict[str, object]]:
    staff_number = required(supplied, "staffNum", "员工号")
    name = required(supplied, "staffName", "姓名")
    if record.full_id == "flight-detail.query-history":
        response, headers, rows = protocol.request_history(staff_number, name)
        return response, {
            "summary": {"recordCount": len(rows), "fieldCount": len(headers)},
            "tables": [{"id": "flight-history", "title": "飞行经历时间", "columns": headers, "rows": rows}],
        }
    month = required(supplied, "startStr", "查询月份")
    timeline = protocol.request_timeline(staff_number, name)
    response, headers, rows = protocol.request_month(staff_number, name, month, timeline)
    return response, {
        "summary": {"month": month, "recordCount": len(rows), "timelineCount": len(timeline)},
        "tables": [{
            "id": "flight-detail",
            "title": "月度航班明细",
            "columns": headers,
            "rows": rows,
        }],
    }
