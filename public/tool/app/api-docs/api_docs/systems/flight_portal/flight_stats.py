from __future__ import annotations

from ieb_protocol.flight_stats import FlightStatsProtocol

from ...catalog import EndpointRecord


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: FlightStatsProtocol,
) -> tuple[object, dict[str, object]]:
    response, headers, row = protocol.request_query(
        str(supplied.get("staffNum") or "").strip(),
        str(supplied.get("startStr") or "").strip(),
        str(supplied.get("endStr") or "").strip(),
    )
    return response, {
        "summary": {"recordCount": 1},
        "tables": [{
            "id": "flight-stats",
            "title": "飞行经历查询结果",
            "columns": headers,
            "rows": [row],
        }],
    }
