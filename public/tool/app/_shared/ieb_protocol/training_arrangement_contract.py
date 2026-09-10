from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup

from .base import IebContractError
from .personnel_contract import _table_data
from .training_arrangement_models import TrainingOption, TrainingPage, TrainingWindow


TRAINING_PAGE_PATH = "/newieb/train/showArrangementPageNew"
ARRANGEMENT_PATH = "/newieb/train/showArrangementList"
ARRANGEMENT_HEADERS = [
    "#", "选择", "训练大纲", "训练科目", "员工号/姓名", "申请描述", "检查项",
    "注册基地", "运行基地", "所属分部", "审批过程", "录入结果", "训练状态",
    "检查员", "检查日期", "航班信息",
]
DISPLAY_HEADERS = ARRANGEMENT_HEADERS[2:]
PERIOD_LABELS = {"week": "周", "month": "月", "year": "年"}


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _has_employee_identity(value: object) -> bool:
    match = re.fullmatch(r"\d+\s*[（(]([^()（）]+)[）)]", _text(value))
    return match is not None and bool(_text(match.group(1)))


def parse_training_options(html: str) -> list[TrainingOption]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    select = soup.select_one("#trainItemArraySelId")
    if select is None:
        raise IebContractError("训练安排页面缺少训练类别选项")
    result: list[TrainingOption] = []
    seen: set[str] = set()
    for option in select.find_all("option"):
        value = _text(option.get("value"))
        label = _text(option.get_text(" ", strip=True))
        if not value or not label or value in seen:
            continue
        seen.add(value)
        result.append(TrainingOption(value, label))
    if not result:
        raise IebContractError("训练安排页面没有可用训练类别")
    return result


def build_query_params(category: str, start: date | str, end: date | str, page: int = 1) -> dict[str, str]:
    category_value = _text(category)
    if not category_value:
        raise ValueError("请选择训练类别")
    start_value = start.isoformat() if isinstance(start, date) else _text(start)
    end_value = end.isoformat() if isinstance(end, date) else _text(end)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_value) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_value):
        raise ValueError("日期必须使用 YYYY-MM-DD")
    if start_value > end_value:
        raise ValueError("开始日期不能晚于结束日期")
    if int(page) < 1:
        raise ValueError("页码必须从 1 开始")
    return {
        "personName": "",
        "trainNavArray": "",
        "baseArray": "",
        "trainItemArray": category_value,
        "classDescription": "",
        "checkStartDt": start_value,
        "checkEndDt": end_value,
        "qtype": "",
        "page": str(int(page)),
    }


def period_windows(end: date, period: str = "all") -> list[tuple[str, str, date, date]]:
    normalized = _text(period).lower() or "all"
    if normalized not in {"all", *PERIOD_LABELS}:
        raise ValueError("时间范围必须是 week、month、year 或 all")
    values = {
        "week": ("week", PERIOD_LABELS["week"], end - timedelta(days=7), end),
        "month": ("month", PERIOD_LABELS["month"], end.replace(day=1), end),
        "year": ("year", PERIOD_LABELS["year"], end.replace(month=1, day=1), end),
    }
    return [values[key] for key in ("week", "month", "year") if normalized == "all" or normalized == key]


def _page_total(text: str) -> int | None:
    match = re.search(r"共\s*([\d,]+)\s*条记录", text)
    return int(match.group(1).replace(",", "")) if match else None


def _page_number(soup: BeautifulSoup, fallback: int) -> int:
    node = soup.select_one("#userPage")
    try:
        return int(node.get("value") or fallback) if node else fallback
    except (TypeError, ValueError):
        return fallback


def parse_training_page(html: str, requested_page: int = 1) -> TrainingPage:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    root = soup.select_one("#showArrangementListJspId")
    if root is None:
        raise IebContractError("训练安排响应缺少结果区域")
    headers, rows = _table_data(root)
    headers = ["选择" if header == "列2" else header for header in headers]
    if headers != ARRANGEMENT_HEADERS:
        raise IebContractError(f"训练安排表头异常：{headers}")
    projected: list[dict[str, str]] = []
    for source in rows:
        row = {key: source.get(key, "") for key in DISPLAY_HEADERS}
        if not _has_employee_identity(row.get("员工号/姓名")):
            continue
        projected.append(row)
    rows = projected
    headers = DISPLAY_HEADERS
    page = _page_number(soup, requested_page)
    return TrainingPage(headers, rows, page, _page_total(soup.get_text(" ", strip=True)))


def row_fingerprint(row: dict[str, str]) -> str:
    payload = "\x1f".join(f"{key}={row.get(key, '')}" for key in DISPLAY_HEADERS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def window_result(
    key: str,
    label: str,
    start: date,
    end: date,
    pages: list[TrainingPage],
) -> TrainingWindow:
    headers = pages[0].headers if pages else list(ARRANGEMENT_HEADERS)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in pages:
        for row in page.rows:
            fingerprint = row_fingerprint(row)
            if fingerprint not in seen:
                seen.add(fingerprint)
                rows.append(row)
    return TrainingWindow(key, label, start, end, headers, rows, len(pages), len(rows))


def display_window(window: TrainingWindow) -> dict[str, Any]:
    return {
        "key": window.key,
        "label": window.label,
        "startDate": window.start.isoformat(),
        "endDate": window.end.isoformat(),
        "pages": window.pages,
        "total": window.total if window.total is not None else len(window.rows),
        "headers": window.headers,
        "rows": window.rows,
    }
