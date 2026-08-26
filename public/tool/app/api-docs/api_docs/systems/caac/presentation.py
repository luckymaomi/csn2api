from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ExecutionError


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def _dynamic_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            name = str(key)
            if name not in columns:
                columns.append(name)
    return columns


def _table_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, str]]:
    return [{column: _display(row.get(column)) for column in columns} for row in rows]


def parse_pilot_list(payload: object, supplied: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ExecutionError("CAAC 列表响应结构异常")
    rows = payload["rows"]
    if any(not isinstance(row, dict) for row in rows):
        raise ExecutionError("CAAC 列表 rows 包含非对象记录")
    typed_rows = [row for row in rows if isinstance(row, dict)]
    columns = _dynamic_columns(typed_rows)
    return {
        "summary": {
            "total": int(payload.get("total") or 0),
            "recordCount": len(typed_rows),
            "page": int(supplied.get("page") or 1),
            "pageSize": int(supplied.get("rows") or 10),
        },
        "tables": [{
            "id": "pilot-list", "title": "有效飞行员分页列表", "columns": columns,
            "rows": _table_rows(typed_rows, columns),
        }],
    }


def _nested_table(key: str, value: object) -> dict[str, object]:
    if isinstance(value, dict):
        rows = [value]
        columns = _dynamic_columns(rows)
        rendered = _table_rows(rows, columns)
    elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
        rows = [item for item in value if isinstance(item, dict)]
        columns = _dynamic_columns(rows)
        rendered = _table_rows(rows, columns)
    elif isinstance(value, list):
        columns = ["值"]
        rendered = [{"值": _display(item)} for item in value]
    else:
        columns = ["值"]
        rendered = [{"值": _display(value)}]
    return {
        "id": f"detail-{re.sub(r'[^a-zA-Z0-9_-]+', '-', key).strip('-') or 'field'}",
        "title": key,
        "columns": columns,
        "rows": rendered,
    }


def parse_pilot_detail(payload: object, lookup: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ExecutionError("CAAC 详情响应结构异常")
    scalar_fields = {
        str(key): _display(value) for key, value in payload.items()
        if not isinstance(value, (dict, list))
    }
    nested_fields = {
        str(key): value for key, value in payload.items()
        if isinstance(value, (dict, list))
    }
    nested_record_count = sum(
        len(value) if isinstance(value, list) else 1 for value in nested_fields.values()
    )
    tables: list[dict[str, object]] = [{
        "id": "pilot-detail", "title": "飞行员详情", "columns": list(scalar_fields),
        "rows": [scalar_fields],
    }]
    tables.extend(_nested_table(key, value) for key, value in nested_fields.items())
    return {
        "summary": {
            "matchedListRows": int(lookup.get("matchedListRows") or 0),
            "scannedListRows": int(lookup.get("scannedListRows") or 0),
            "topLevelKeyCount": len(payload),
            "scalarFieldCount": len(scalar_fields),
            "nestedFieldCount": len(nested_fields),
            "nestedRecordCount": nested_record_count,
        },
        "tables": tables,
    }


__all__ = ["parse_pilot_detail", "parse_pilot_list"]
