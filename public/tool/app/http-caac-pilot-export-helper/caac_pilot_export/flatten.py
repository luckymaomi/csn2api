from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

from .field_mappings import RECORD_SPECS, TOP_LEVEL_FIELD_LABELS, TREE_FIELD_LABELS, RecordSpec


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
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?i)</?br\s*/?>", "\n", unescape(text))
    return text.strip()


def _unknown_label(key: str) -> str:
    return f"未映射字段（{key}）"


def _nested_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return _scalar(value)


def _tree_lines(value: Any, depth: int = 0) -> list[str]:
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            lines.extend(_tree_lines(item, depth))
        return lines
    if not isinstance(value, dict):
        text = _scalar(value)
        return [("  " * depth) + text] if text else []

    parts: list[str] = []
    for key, label in TREE_FIELD_LABELS.items():
        text = _nested_value(value.get(key))
        if not text:
            continue
        parts.append(text if key == "layerinfo" else f"{label}：{text}")
    for key, raw in value.items():
        if key in TREE_FIELD_LABELS or key == "sublayers":
            continue
        text = _nested_value(raw)
        if text:
            parts.append(f"{_unknown_label(key)}：{text}")
    own = [("  " * depth) + "；".join(parts)] if parts else []
    return own + _tree_lines(value.get("sublayers"), depth + 1)


def _record_text(value: Any, spec: RecordSpec) -> str:
    if not isinstance(value, list):
        return _nested_value(value)
    rows: list[str] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            text = _scalar(item)
            if text:
                rows.append(f"{index}. {text}")
            continue
        parts: list[str] = []
        for key, label in spec.fields.items():
            text = _nested_value(item.get(key))
            if text:
                parts.append(f"{label}：{text}")
        for key, raw in item.items():
            if key in spec.fields:
                continue
            text = _nested_value(raw)
            if text:
                parts.append(f"{_unknown_label(key)}：{text}")
        if parts:
            rows.append(f"{index}. " + "；".join(parts))
    return "\n".join(rows)


def _flatten_scalars(payload: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, label in TOP_LEVEL_FIELD_LABELS.items():
        if key not in payload or isinstance(payload[key], (list, dict)):
            continue
        flattened[label] = _scalar(payload[key])
    for key, value in payload.items():
        if key in TOP_LEVEL_FIELD_LABELS or isinstance(value, (list, dict)):
            continue
        flattened[_unknown_label(key)] = _scalar(value)
    return flattened


def flatten_detail(detail: dict[str, Any]) -> dict[str, str]:
    flattened = _flatten_scalars(detail)
    if "layerInfosList" in detail:
        flattened["执照等级"] = "\n".join(_tree_lines(detail["layerInfosList"]))
    for key, value in detail.items():
        if key == "layerInfosList" or not isinstance(value, (list, dict)):
            continue
        spec = RECORD_SPECS.get(key)
        if spec:
            flattened[spec.label] = _record_text(value, spec)
        else:
            flattened[_unknown_label(key)] = _nested_value(value)
    return flattened


def flatten_listing(listing: dict[str, Any]) -> dict[str, str]:
    flattened = _flatten_scalars(listing)
    for key, value in listing.items():
        if isinstance(value, (list, dict)):
            flattened[_unknown_label(key)] = _nested_value(value)
    return flattened
