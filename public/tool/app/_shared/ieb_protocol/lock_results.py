from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, Tag

from .base import IebContractError
from .lock_metadata import normalize_lock_type, normalize_text
from .lock_models import EmployeeIdentity, LockSubmission, PortalMetadata, SubmitResult


STATUS_CODES = {"已锁": "1", "待审批": "3", "已解锁": "5", "已撤销": "6", "已否决": "7"}


def _cell_texts(row: Tag) -> list[str]:
    return [normalize_text(cell.get_text(" ", strip=True)) for cell in row.select(":scope > th, :scope > td")]


def _table_headers(root: Tag) -> list[str]:
    for selector in ("thead th", ".hDiv th", "tr th"):
        values = [normalize_text(cell.get_text(" ", strip=True)) for cell in root.select(selector)]
        if values and any(values):
            headers = [value or ("选择" if index == 0 else f"列{index + 1}") for index, value in enumerate(values)]
            if len(set(headers)) != len(headers):
                raise IebContractError("门户结果表存在重复表头")
            return headers
    return []


def _table_rows(root: Tag, headers: list[str]) -> list[dict[str, str]]:
    nodes: list[Tag] = []
    for selector in (".bDiv tbody tr", "tbody.list tr", "tbody tr"):
        nodes = list(root.select(selector))
        if nodes:
            break
    rows: list[dict[str, str]] = []
    for node in nodes:
        values = _cell_texts(node)
        if len(values) == len(headers) + 1 and re.fullmatch(r"\d{1,5}", values[0] or ""):
            values = values[1:]
        row_text = " | ".join(value for value in values if value)
        if not values or "没有相关信息" in row_text:
            continue
        if len(values) != len(headers):
            raise IebContractError("门户结果表头与数据列数不一致")
        row = dict(zip(headers, values))
        checkbox = node.select_one("input[type='checkbox'][value]")
        if checkbox is not None:
            row["记录ID"] = normalize_text(checkbox.get("value"))
        row["_text"] = row_text
        rows.append(row)
    return rows


def _section(
    soup: BeautifulSoup,
    selector: str,
    *fallback_selectors: str,
) -> tuple[list[str], list[dict[str, str]]]:
    root = soup.select_one(selector)
    if root is None:
        for candidate in fallback_selectors:
            root = soup.select_one(candidate)
            if root is not None:
                break
    if root is None:
        raise IebContractError(f"门户响应缺少结果区域 {selector}")
    headers = _table_headers(root)
    if not headers:
        raise IebContractError(f"门户响应的结果区域 {selector} 缺少表头")
    return headers, _table_rows(root, headers)


def parse_submit_result(html: str) -> SubmitResult:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    _headers, result_rows = _section(
        soup,
        "#showNonproductionTaskImportResultPage1",
        "#showNonproductionTaskImportResultPage1table",
    )
    conflict_headers, conflict_rows = _section(soup, "#showNonproductionTaskImportResultPage2")
    if conflict_rows and "冲突" not in conflict_headers:
        raise IebContractError("门户冲突结果缺少“冲突”列")
    return SubmitResult(result_rows, conflict_rows)


def parse_quota_result(html: str) -> tuple[list[str], list[dict[str, str]]]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    header_root = soup.select_one(".hDiv table")
    body_root = soup.select_one(".bDiv table")
    if header_root is None or body_root is None:
        raise IebContractError("休假额度响应缺少表格结构")
    headers = _table_headers(header_root)
    if not headers:
        raise IebContractError("休假额度响应缺少表头")
    return headers, _table_rows(body_root, headers)


def _field(row: dict[str, str], *aliases: str) -> str:
    return next((normalize_text(row.get(alias)) for alias in aliases if normalize_text(row.get(alias))), "")


def _portal_datetime(value: object) -> str:
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?::\d{2})?", normalize_text(value))
    return f"{match.group(1)} {match.group(2)}" if match else ""


def _same_name(left: object, right: object) -> bool:
    clean = lambda value: re.sub(r"\s+|[（(][^）)]*[）)]", "", normalize_text(value)).upper()
    return clean(left) == clean(right)


def _row_matches(
    row: dict[str, str],
    submission: LockSubmission,
    identity: EmployeeIdentity,
    metadata: PortalMetadata,
    expected_range: tuple[str, str],
) -> bool:
    if _field(row, "员工号", "员工编号") != identity.employee_id or not _same_name(_field(row, "姓名"), identity.name):
        return False
    row_type = _field(row, "锁班类型", "锁班名称")
    normalized = normalize_lock_type(row_type, metadata)
    item = metadata.lock_types.get(submission.lock_type)
    if normalized != submission.lock_type and (item is None or normalize_text(item.description) not in normalize_text(row_type)):
        return False
    return (
        _portal_datetime(_field(row, "开始日期", "开始时间")) == expected_range[0]
        and _portal_datetime(_field(row, "结束日期", "结束时间")) == expected_range[1]
    )


def attribute_rows(
    rows: Iterable[dict[str, str]],
    submission: LockSubmission,
    identity: EmployeeIdentity,
    metadata: PortalMetadata,
    label: str,
) -> tuple[list[dict[str, str]], str]:
    remaining = list(rows)
    matched: list[dict[str, str]] = []
    for expected_range in submission.expected_ranges():
        candidates = [row for row in remaining if _row_matches(row, submission, identity, metadata, expected_range)]
        if len(candidates) != 1:
            return [], f"{label}无法按员工、类型和日期时间精确归属"
        matched.append(candidates[0])
        remaining.remove(candidates[0])
    return matched, ""


def query_form(employee_id: str, status: str, page: int, random_value: str) -> dict[str, str]:
    return {
        "staffnum": employee_id, "base": "", "primBase": "", "fleetCd": "", "lockType": "",
        "lockStatus": STATUS_CODES.get(status, status), "startDt": "", "endDt": "", "orderByType": "0",
        "entryStaffnum": "", "page": str(page), "random": random_value,
    }


def parse_query_result(html: str) -> tuple[list[dict[str, str]], int]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    root = soup.select_one(".flexigrid") or soup
    headers = _table_headers(root)
    if not headers:
        raise IebContractError("锁班查询响应缺少表头")
    rows = _table_rows(root, headers)
    page_count = 1
    for link in soup.select("a"):
        if normalize_text(link.get_text(" ", strip=True)) == "最后一页":
            values = re.findall(r"goPageTwo\([^)]*,\s*['\"]?(\d+)['\"]?\s*\)\s*;?", normalize_text(link.get("href")))
            if values:
                page_count = int(values[-1])
                break
    if page_count == 1:
        values = [int(value) for pattern in (r"(?:page=|changePage\s*\(\s*['\"]?)(\d+)", r"goPageTwo\([^)]*,\s*['\"]?(\d+)['\"]?\s*\)") for value in re.findall(pattern, html, re.I)]
        if values:
            page_count = max(page_count, *values)
    return rows, page_count


def same_query_identity(left: dict[str, str], right: dict[str, str]) -> bool:
    left_id, right_id = normalize_text(left.get("记录ID")), normalize_text(right.get("记录ID"))
    if left_id and right_id:
        return left_id == right_id
    fields = ("员工号", "姓名", "开始日期", "结束日期", "锁班类型", "录入时间")
    return all(normalize_text(left.get(name)) == normalize_text(right.get(name)) for name in fields)
