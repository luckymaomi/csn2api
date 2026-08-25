from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


CAAC_TIMEZONE = timezone(timedelta(hours=8))


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 100_000_000_000 <= abs(value) <= 100_000_000_000_000:
            try:
                return datetime.fromtimestamp(value / 1000, CAAC_TIMEZONE).date().isoformat()
            except (OSError, OverflowError, ValueError):
                pass
        return str(value)
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _tree_lines(value: Any, depth: int = 0) -> list[str]:
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            lines.extend(_tree_lines(item, depth))
        return lines
    if isinstance(value, dict):
        label = _scalar(value.get("layerinfo") or value.get("name") or value.get("title"))
        own = [("  " * depth) + label] if label else []
        return own + _tree_lines(value.get("sublayers"), depth + 1)
    return [_scalar(value)] if value not in (None, "") else []


def _nested_text(value: Any) -> str:
    if isinstance(value, list):
        rows = []
        for item in value:
            if isinstance(item, dict):
                parts = [f"{key}={_scalar(item[key])}" for key in item if not isinstance(item[key], (dict, list)) and _scalar(item[key])]
                nested = [f"{key}=[{_nested_text(item[key])}]" for key in item if isinstance(item[key], (dict, list)) and _nested_text(item[key])]
                rows.append("; ".join(parts + nested))
            else:
                rows.append(_scalar(item))
        return "\n".join(row for row in rows if row)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return _scalar(value)


def flatten_detail(detail: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in detail.items():
        if key == "layerInfosList":
            flattened["详情.layerInfosList.资质层级"] = "\n".join(_tree_lines(value))
        elif isinstance(value, (list, dict)):
            flattened[f"详情.{key}"] = _nested_text(value)
        else:
            flattened[f"详情.{key}"] = _scalar(value)
    return flattened


def flatten_listing(listing: dict[str, Any]) -> dict[str, str]:
    return {f"列表.{key}": _scalar(value) for key, value in listing.items() if not isinstance(value, (list, dict))}
