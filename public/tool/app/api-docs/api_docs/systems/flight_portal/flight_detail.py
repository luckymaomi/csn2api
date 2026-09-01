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
