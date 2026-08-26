from __future__ import annotations

from ieb_protocol.qualification_monitor import QualificationMonitorProtocol
from ieb_protocol.qualification_monitor_contract import display_rows

from ...catalog import EndpointRecord


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: QualificationMonitorProtocol,
) -> tuple[object, dict[str, object]]:
    code = next(
        (
            str(item.get("default") or "").strip()
            for item in record.endpoint.get("parameters", [])
            if isinstance(item, dict) and item.get("name") == "qualType" and item.get("fixed")
        ),
        "",
    )
    response, page = protocol.request_page(
        code,
        supplied,
        supplied.get("pageNum", 1),
        supplied.get("pageSize", 20),
    )
    rows = display_rows(page.rows)
    return response, {
        "summary": {
            "recordCount": len(rows),
            "total": page.total,
            "pages": page.pages,
            "pageNum": page.page_number,
            "pageSize": page.page_size,
            "hasNextPage": page.has_next_page,
        },
        "tables": [{
            "id": "qualification-monitor",
            "title": "资质监控查询结果",
            "columns": page.columns,
            "rows": rows,
        }],
    }
