from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Mapping

from .base import IebContractError
from .qualification_monitor_models import QualificationGroup, QualificationItem, QualificationPage


EXPECTED_GROUPS = {
    "ZZYX": "资质运行类",
    "ZZZG": "资质资格类",
    "ZZTS": "资质特殊类",
}
FILTER_NAMES = (
    "staffNum",
    "alarmType",
    "primaryBase",
    "manyStaffNum",
    "manyAlarmType",
    "base",
    "fleetCd",
    "allClear",
    "effective",
    "effectiveModel",
)
OOXML_REQUIRED_PARTS = {"[Content_Types].xml", "xl/workbook.xml"}


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_classification_tree(payload: object) -> list[QualificationGroup]:
    if not isinstance(payload, list):
        raise IebContractError("资质分类接口未返回 JSON 数组")
    groups: list[QualificationGroup] = []
    group_codes: set[str] = set()
    item_codes: set[str] = set()
    for raw_group in payload:
        if not isinstance(raw_group, dict):
            raise IebContractError("资质分类父项结构异常")
        code = _text(raw_group.get("msgCode"))
        name = _text(raw_group.get("msgType"))
        children = raw_group.get("sonList")
        if code not in EXPECTED_GROUPS or code in group_codes:
            raise IebContractError(f"资质分类父项异常：{code or '缺少代码'}")
        if name != EXPECTED_GROUPS[code] or not isinstance(children, list) or not children:
            raise IebContractError(f"资质分类父项契约异常：{code}")
        items: list[QualificationItem] = []
        for raw_item in children:
            if not isinstance(raw_item, dict):
                raise IebContractError(f"资质分类子项结构异常：{code}")
            item_code = _text(raw_item.get("msgCode"))
            item_name = _text(raw_item.get("msgType"))
            if not item_code or not item_name or item_code in item_codes:
                raise IebContractError(f"资质分类子项缺失或重复：{item_code or '缺少代码'}")
            item_codes.add(item_code)
            items.append(QualificationItem(item_name, item_code))
        group_codes.add(code)
        groups.append(QualificationGroup(name, code, items))
    if group_codes != set(EXPECTED_GROUPS):
        missing = ", ".join(code for code in EXPECTED_GROUPS if code not in group_codes)
        raise IebContractError(f"资质分类缺少父项：{missing}")
    return groups


def build_filter_params(qualification_code: str, filters: Mapping[str, object] | None = None) -> list[tuple[str, str]]:
    code = _text(qualification_code)
    if not code:
        raise ValueError("资质代码不能为空")
    supplied = filters or {}
    return [("qualType", code), *((name, _text(supplied.get(name))) for name in FILTER_NAMES)]


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是正整数")
    text = str(value or "").strip()
    if not text.isdigit() or int(text) < 1:
        raise ValueError(f"{label}必须是正整数")
    return int(text)


def build_query_params(
    qualification_code: str,
    filters: Mapping[str, object] | None = None,
    page_number: object = 1,
    page_size: object = 20,
) -> list[tuple[str, str]]:
    page = _positive_integer(page_number, "页码")
    size = _positive_integer(page_size, "每页条数")
    return [
        *build_filter_params(qualification_code, filters),
        ("pageNum", str(page)),
        ("pageSize", str(size)),
    ]


def parse_page_info(payload: object) -> QualificationPage:
    if not isinstance(payload, dict) or not isinstance(payload.get("list"), list):
        raise IebContractError("资质查询 PageInfo 结构异常")
    raw_rows = payload["list"]
    if any(not isinstance(row, dict) for row in raw_rows):
        raise IebContractError("资质查询结果行结构异常")

    def non_negative(name: str) -> int:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IebContractError(f"资质查询 PageInfo 字段异常：{name}")
        return value

    total = non_negative("total")
    pages = non_negative("pages")
    page_number = non_negative("pageNum")
    page_size = non_negative("pageSize")
    has_next = payload.get("hasNextPage")
    if not isinstance(has_next, bool):
        raise IebContractError("资质查询 PageInfo 字段异常：hasNextPage")
    if page_number < 1 or page_size < 1 or len(raw_rows) > page_size:
        raise IebContractError("资质查询 PageInfo 页码契约异常")
    if total == 0 and (raw_rows or pages != 0 or has_next):
        raise IebContractError("资质查询空结果分页契约异常")
    if total > 0 and pages < 1:
        raise IebContractError("资质查询总页数契约异常")
    return QualificationPage(
        rows=[dict(row) for row in raw_rows],
        total=total,
        pages=pages,
        page_number=page_number,
        page_size=page_size,
        has_next_page=has_next,
    )


def validate_ooxml(content: bytes) -> bytes:
    if not isinstance(content, bytes) or not content.startswith(b"PK"):
        raise IebContractError("门户导出未返回 OOXML 文件")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if not OOXML_REQUIRED_PARTS.issubset(names):
                raise IebContractError("门户导出缺少 OOXML 必要部件")
            if not any(name.startswith("xl/worksheets/") and name.endswith(".xml") for name in names):
                raise IebContractError("门户导出缺少 worksheet")
            for name in OOXML_REQUIRED_PARTS:
                archive.read(name)
    except IebContractError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise IebContractError("门户导出不是有效 OOXML 文件") from error
    return content


def display_rows(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    import json

    return [
        {
            str(name): json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list)) else value
            for name, value in row.items()
        }
        for row in rows
    ]
