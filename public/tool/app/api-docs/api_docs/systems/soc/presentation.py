from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from soc_protocol import FlightOption, SubmitOutcome


def _display(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            name = str(key)
            if name not in columns:
                columns.append(name)
    return columns


def _table(table_id: str, title: str, rows: list[dict[str, Any]]) -> dict[str, object]:
    columns = _columns(rows)
    return {
        "id": table_id,
        "title": title,
        "columns": columns,
        "rows": [{column: _display(row.get(column)) for column in columns} for row in rows],
    }


def present_json(payload: object) -> dict[str, object]:
    tables: list[dict[str, object]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                tables.append(_table(str(key), str(key), [item for item in value if isinstance(item, dict)]))
            elif isinstance(value, list):
                tables.append(_table(str(key), str(key), [{"值": item} for item in value]))
        if not tables:
            tables.append(_table("response", "响应字段", [{str(key): value for key, value in payload.items()}]))
        summary: dict[str, object] = {"responseKeys": [str(key) for key in payload]}
    elif isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
        tables = [_table("response", "响应列表", rows)] if rows else [
            _table("response", "响应列表", [{"值": item} for item in payload])
        ]
        summary = {"recordCount": len(payload)}
    else:
        summary = {"value": _display(payload)}
    return {"summary": summary, "tables": tables, "json": payload}


def present_suggestions(suggestions: list[str]) -> dict[str, object]:
    return {
        "summary": {"candidateCount": len(suggestions)},
        "tables": [_table("station-suggestions", "站点建议", [{"站点": item} for item in suggestions])],
        "json": {"result": suggestions},
    }


def present_flights(options: list[FlightOption]) -> dict[str, object]:
    labels = {
        "display_number": "显示航班号", "flight_number": "航班号", "sequence_number": "内部航班序号",
        "flight_date": "航班日期", "route": "航线", "flight_time": "航班时间",
        "crew_departure": "机组出发时间", "subfleet_type": "机型", "airline_code": "承运人",
        "value": "动态航班复合值",
    }
    rows = [{labels[key]: value for key, value in asdict(option).items()} for option in options]
    return {
        "summary": {"flightCount": len(options)},
        "tables": [_table("flights", "动态航班", rows)],
        "json": rows,
    }


def present_submit(payload: object, outcome: SubmitOutcome) -> dict[str, object]:
    return {
        "summary": {"success": outcome.success, "message": outcome.message},
        "tables": [_table("submit-result", "提交结果", [{"业务成功": outcome.success, "业务消息": outcome.message}])],
        "json": payload,
    }


__all__ = ["present_flights", "present_json", "present_submit", "present_suggestions"]
