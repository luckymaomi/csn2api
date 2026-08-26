from __future__ import annotations

from ieb_protocol.personnel import PersonnelProtocol
from ieb_protocol.personnel_contract import TRAINING_RECORD_HEADERS, parse_detail_table

from ...catalog import EndpointRecord
from .common import required


def _rows_data(table_id: str, title: str, rows: list[dict[str, str]]) -> dict[str, object]:
    columns = list(rows[0].keys()) if rows else []
    return {
        "summary": {"recordCount": len(rows)},
        "tables": [{"id": table_id, "title": title, "columns": columns, "rows": rows}],
    }


def _basic_data(basic: dict[str, object]) -> dict[str, object]:
    table_ids = {
        "基本信息": "empDto",
        "教育经历": "eduList",
        "工作经历": "workList",
        "职称信息": "titleList",
        "家庭信息": "relationList",
    }
    tables: list[dict[str, object]] = []
    for title, value in basic.items():
        rows = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
        columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
        tables.append({"id": table_ids.get(title, title), "title": title, "columns": columns, "rows": rows})
    return {
        "summary": {"sectionCount": len(tables), "recordCount": sum(len(table["rows"]) for table in tables)},
        "tables": tables,
    }


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: PersonnelProtocol,
) -> tuple[object, dict[str, object]]:
    if record.full_id == "personnel-info.basic":
        response, basic = protocol.request_basic(required(supplied, "staffNum", "员工号"))
        return response, _basic_data(basic)
    if record.full_id == "personnel-info.technical":
        response, rows = protocol.request_technical(required(supplied, "staffNum", "员工号"))
        return response, _rows_data("technical", "技术等级", rows)
    if record.full_id == "personnel-info.operation":
        response, rows = protocol.request_operation(required(supplied, "empid", "员工号"))
        return response, _rows_data("operation", "运行资格", rows)
    if record.full_id == "personnel-info.training-records":
        response = protocol.request_training_record_page(
            required(supplied, "staffId", "员工号"),
            int(supplied.get("page") or 1),
        )
        rows = parse_detail_table(str(response.text or ""), "#showTrainingRecordListDiv", TRAINING_RECORD_HEADERS)
        return response, _rows_data("training-records", "培训记录", rows)
    response, rows = protocol.request_training_experiences(required(supplied, "staffNum", "员工号"))
    return response, _rows_data("training-experiences", "训练经历", rows)
