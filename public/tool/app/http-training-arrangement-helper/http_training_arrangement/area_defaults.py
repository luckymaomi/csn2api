from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ieb_protocol.training_arrangement_models import TrainingOption
from ieb_protocol.training_arrangement_contract import row_fingerprint
from .models import AreaWindow


@dataclass(frozen=True)
class AreaCategory:
    name: str
    subjects: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedAreaCategory:
    name: str
    subjects: tuple[TrainingOption, ...]


AREA_DEFAULTS: tuple[AreaCategory, ...] = (
    AreaCategory("区域航线", ("特殊区域、航路和机场训练",)),
    AreaCategory("区域报务", ("英语通信单飞航线检查",)),
    AreaCategory("副驾驶转A2", ("副驾驶转标准训练(A2)",)),
    AreaCategory("副驾驶转B", ("副驾驶转标准训练(B)",)),
    AreaCategory("副驾驶转C", ("副驾驶转标准训练(C)",)),
    AreaCategory("副驾驶转D", ("副驾驶转标准训练(D)",)),
    AreaCategory("机长年度", ("机长年度航线检查",)),
    AreaCategory(
        "航线一检",
        (
            "STC机长转机型一级航检",
            "非STC机长转机型一级航检（大转重）",
            "非STC机长转机型一级航检（非大转重）",
        ),
    ),
    AreaCategory("航线二检", ("非STC机长转机型二级航检",)),
    AreaCategory("机长转C", ("机长等级训练B转C",)),
    AreaCategory("机长转D", ("机长等级训练C转D",)),
)


def _normalize(value: object) -> str:
    return "".join(str(value or "").split())


def resolve_area_defaults(options: Iterable[TrainingOption]) -> list[ResolvedAreaCategory]:
    available: dict[str, list[TrainingOption]] = {}
    for option in options:
        available.setdefault(_normalize(option.label), []).append(option)
    resolved: list[ResolvedAreaCategory] = []
    missing: list[str] = []
    duplicate: list[str] = []
    for category in AREA_DEFAULTS:
        subjects: list[TrainingOption] = []
        for label in category.subjects:
            matches = available.get(_normalize(label), [])
            if not matches:
                missing.append(label)
            elif len(matches) > 1:
                duplicate.append(label)
            else:
                subjects.append(matches[0])
        if len(subjects) == len(category.subjects):
            resolved.append(ResolvedAreaCategory(category.name, tuple(subjects)))
    if missing or duplicate:
        details = []
        if missing:
            details.append(f"缺少：{'、'.join(missing)}")
        if duplicate:
            details.append(f"重复：{'、'.join(duplicate)}")
        raise ValueError("区域默认配置无法匹配当前训练类别（" + "；".join(details) + "）")
    return resolved


def outcome(row: dict[str, str]) -> str:
    status = str(row.get("训练状态", "") or "").strip()
    if status == "终止":
        return "failed"
    if status == "完成":
        return "passed"
    raise ValueError(f"训练状态不受支持：{status or '空值'}")


def area_summary(categories: Iterable[ResolvedAreaCategory], windows: Iterable[object]) -> list[dict[str, object]]:
    rows = list(windows)
    result: list[dict[str, object]] = []
    for category in categories:
        periods: dict[str, dict[str, object]] = {}
        for key in ("week", "month", "year"):
            matched = [window for window in rows if getattr(window, "category", "") == category.name and getattr(window, "key", "") == key]
            detail_rows = [row for window in matched for row in getattr(window, "rows", [])]
            count = len(detail_rows)
            passed = sum(1 for row in detail_rows if outcome(row) == "passed")
            periods[key] = {
                "count": count,
                "passed": passed,
                "rate": round(passed / count * 100, 1) if count else None,
            }
        result.append({"type": category.name, **periods})
    return result


def merge_area_windows(windows: Iterable[AreaWindow]) -> list[AreaWindow]:
    merged: dict[tuple[str, str], AreaWindow] = {}
    for window in windows:
        key = (window.category, window.key)
        current = merged.get(key)
        if current is None:
            merged[key] = window
            continue
        total = None if current.total is None or window.total is None else current.total + window.total
        headers = list(current.headers)
        for header in window.headers:
            if header not in headers:
                headers.append(header)
        combined_rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in [*current.rows, *window.rows]:
            fingerprint = row_fingerprint(row)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            combined_rows.append(row)
        merged[key] = AreaWindow(
            current.category,
            current.key,
            current.label,
            current.start,
            current.end,
            headers,
            combined_rows,
            current.pages + window.pages,
            total,
        )
    return list(merged.values())


def area_details(windows: Iterable[AreaWindow]) -> tuple[list[str], list[dict[str, str]]]:
    period_order = {"week": 0, "month": 1, "year": 2}
    details: dict[tuple[str, str], tuple[dict[str, str], set[tuple[int, str]]]] = {}
    portal_headers: list[str] = []
    for window in windows:
        for header in window.headers:
            if header not in {"区域类型", "所属周期"} and header not in portal_headers:
                portal_headers.append(header)
        for row in window.rows:
            key = (window.category, row_fingerprint(row))
            current = details.get(key)
            if current is None:
                current = ({"区域类型": window.category, **row}, set())
                details[key] = current
            current[1].add((period_order.get(window.key, 99), window.label))
    rows: list[dict[str, str]] = []
    for row, periods in details.values():
        row["所属周期"] = "、".join(label for _order, label in sorted(periods))
        rows.append(row)
    return ["区域类型", "所属周期", *portal_headers], rows


__all__ = ["AREA_DEFAULTS", "AreaCategory", "ResolvedAreaCategory", "area_details", "area_summary", "merge_area_windows", "outcome", "resolve_area_defaults"]
