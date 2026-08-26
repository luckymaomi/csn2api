from __future__ import annotations

from ieb_protocol.qualification_roster import QualificationRosterProtocol
from ieb_protocol.roster_contract import parse_ooxml_rows
from ieb_protocol.roster_models import QueryFilters

from ...catalog import EndpointRecord
from ..errors import ExecutionError


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: QualificationRosterProtocol,
) -> tuple[object, dict[str, object]]:
    if record.full_id == "qualification-roster.filter-page":
        response, fields = protocol.request_filter_fields()
        rows = [
            {
                "字段": field.name,
                "字段名称": field.label,
                "是否多选": "是" if field.multiple else "否",
                "选项值": option.value,
                "选项名称": option.label,
            }
            for field in fields
            for option in field.options
        ]
        return response, {
            "summary": {"fieldCount": len(fields), "optionCount": len(rows)},
            "tables": [{
                "id": "filter-fields",
                "title": "动态筛选项",
                "columns": ["字段", "字段名称", "是否多选", "选项值", "选项名称"],
                "rows": rows,
            }],
        }
    if record.full_id == "qualification-roster.operating-qualifications":
        response, qualifications = protocol.request_qualifications()
        rows = [{
            "资格代码": item.code,
            "中文描述": item.name,
            "资格简码": item.short_name,
            "资格类型": item.type_code,
            "类型描述": item.type_name,
        } for item in qualifications]
        return response, {
            "summary": {"recordCount": len(rows)},
            "tables": [{
                "id": "operating-qualifications",
                "title": "动态运行资格",
                "columns": ["资格代码", "中文描述", "资格简码", "资格类型", "类型描述"],
                "rows": rows,
            }],
        }
    if record.full_id == "qualification-roster.query":
        response, total, headers, rows = protocol.request_query(
            QueryFilters.from_payload(supplied),
            str(supplied.get("operQualArray") or ""),
        )
        return response, {
            "summary": {"total": total, "currentPageRows": len(rows)},
            "tables": [{
                "id": "qualification-roster-query",
                "title": "人员查询结果",
                "columns": headers,
                "rows": rows,
            }] if headers else [],
        }
    if record.full_id == "qualification-roster.native-export":
        response, content = protocol.request_export(
            QueryFilters.from_payload(supplied),
            str(supplied.get("operQualArray") or ""),
        )
        headers, rows = parse_ooxml_rows(content)
        return response, {
            "summary": {"ooxml": True, "recordCount": len(rows), "columnCount": len(headers)},
            "tables": [{
                "id": "personnel-export",
                "title": "普通人员清单导出",
                "columns": headers,
                "rows": rows,
            }],
        }
    raise ExecutionError("逐资格合并名册由独立 APP 执行")
