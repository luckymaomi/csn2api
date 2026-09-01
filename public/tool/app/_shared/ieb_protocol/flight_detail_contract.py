from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from .base import IebContractError


DETAIL_HEADERS = [
    "序号", "航班号", "机型", "日期", "左座", "右座", "操纵", "观察",
    "离场", "到达", "飞行时间", "夜航", "飞行阶段", "人工飞行时间", "人工飞行方式",
]
QUERY_PAGE_PATH = "/newieb/flytime/showFlytimeManyQuery"
TIMELINE_PATH = "/newieb/basics/flytimeList"
DETAIL_PATH = "/newieb/flytime/showFlyDetail"


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_month(value: object) -> str:
    if hasattr(value, "year") and hasattr(value, "month"):
        year, month = int(value.year), int(value.month)
    else:
        match = re.fullmatch(r"\s*(\d{4})[/-](\d{1,2})\s*", str(value or ""))
        if not match:
            raise ValueError("月份格式必须为 YYYY/M 或 YYYY/MM")
        year, month = int(match.group(1)), int(match.group(2))
    if year < 1 or not 1 <= month <= 12:
        raise ValueError("月份必须是有效的年月")
    return f"{year:04d}-{month:02d}"


def month_range(start: str, end: str) -> list[str]:
    start_value, end_value = normalize_month(start), normalize_month(end)
    year, month = (int(part) for part in start_value.split("-"))
    end_year, end_month = (int(part) for part in end_value.split("-"))
    if (year, month) > (end_year, end_month):
        raise ValueError("结束年月早于开始年月")
    months: list[str] = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def build_detail_params(staff_number: str, name: str, month: str, fleet: str) -> dict[str, str]:
    return {
        "startStr": normalize_month(month),
        "endStr": "",
        "dateType": "2",
        "staffNum": _text(staff_number),
        "staffName": _text(name),
        "fleetCdArray": _text(fleet),
    }


def _onclick_values(node: Tag) -> dict[str, str] | None:
    onclick = str(node.get("onclick") or "")
    values = onclick.split("'")
    if len(values) < 12 or not values[0].strip().startswith("showflyTimeDetail"):
        return None
    date_type, staff, name, start, end, fleet = (values[index].strip() for index in (1, 3, 5, 7, 9, 11))
    return {"dateType": date_type, "staff": staff, "name": name, "start": start, "end": end, "fleet": fleet}


def parse_timeline(html: str, expected_staff: str, expected_name: str = "") -> list[dict[str, str]]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    entries = [entry for node in soup.select("[onclick]") if (entry := _onclick_values(node))]
    if not entries:
        raise IebContractError("飞行经历时间轴没有返回可用月份")
    matches = [entry for entry in entries if entry["staff"] == _text(expected_staff)]
    if not matches:
        raise IebContractError("时间轴员工号与输入不匹配")
    if expected_name and any(entry["name"] != _text(expected_name) for entry in matches):
        raise IebContractError("时间轴姓名与输入不匹配")
    return matches


def validate_detail_query_page(html: str, status_code: int) -> None:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    if status_code != 200 or soup.select_one("#showflyTimeExperienceQueryForm") is None:
        raise IebContractError("飞行经历查询页没有返回有效表单")


def resolve_month_fleet(entries: Iterable[dict[str, str]], month: str) -> str:
    target = normalize_month(month)
    values = list(entries)
    exact = next((item["fleet"] for item in values if item.get("dateType") == "2" and item.get("start") == target), "")
    if exact:
        return exact
    year = target[:4]
    return next((item["fleet"] for item in values if item.get("dateType") == "1" and item.get("start") == year), "")


def _cell_value(cell: Tag) -> str:
    return _text(cell.get("title") or cell.get_text(" ", strip=True))


def parse_detail_table(html: str) -> tuple[list[str], list[dict[str, str]]]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    for table in soup.select("table"):
        rows = table.select("tr")
        if not rows:
            continue
        header_row = next((row for row in rows if any(_cell_value(cell) == "序号" for cell in row.find_all(["th", "td"], recursive=False))), None)
        if header_row is None:
            continue
        headers = [_cell_value(cell) for cell in header_row.find_all(["th", "td"], recursive=False)]
        if headers != DETAIL_HEADERS:
            raise IebContractError("航班明细表头不符合真实契约")
        data_rows = rows[rows.index(header_row) + 1 :]
        starts: list[int] = []
        values_by_row: list[list[str]] = []
        for index, row in enumerate(data_rows):
            values = [_cell_value(cell) for cell in row.find_all(["th", "td"], recursive=False)]
            values_by_row.append(values)
            if values and values[0].isdigit():
                starts.append(index)
        result: list[dict[str, str]] = []
        for position, start in enumerate(starts):
            stop = starts[position + 1] if position + 1 < len(starts) else len(data_rows)
            values = values_by_row[start]
            if len(values) != len(DETAIL_HEADERS) - 1:
                raise IebContractError(f"航班明细主行列数异常：{len(values)}")
            mode = ""
            for extra_values in values_by_row[start + 1 : stop]:
                if len(extra_values) == 1 and extra_values[0]:
                    mode = extra_values[0]
                    break
            result.append(dict(zip(DETAIL_HEADERS, [*values, mode])))
        return headers, result
    raise IebContractError("响应中未找到航班明细表")
