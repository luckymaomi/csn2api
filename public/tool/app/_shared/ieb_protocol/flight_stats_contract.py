from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup, Tag

from .base import IebContractError


QUERY_PATH = "/newieb/flytime/showFlytimeManyQueryList"


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def validate_query_page(html: str, status_code: int) -> None:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    form = soup.select_one("#showflyTimeExperienceQueryForm")
    if status_code != 200 or form is None or form.get("action") != QUERY_PATH:
        raise IebContractError("飞行经历查询页没有返回有效表单")


def build_query_params(
    staff_number: str,
    start_date: str,
    end_date: str,
    timestamp: str | None = None,
) -> dict[str, str]:
    return {
        "staffNum": _text(staff_number),
        "activeStatusArray": "ZAIZHI",
        "fleetCdArray1": "",
        "fleetCdArray": "",
        "chnDescArray": "",
        "primaryBaseArray": "",
        "baseArray": "",
        "dateType": "5",
        "exportType": "1",
        "startStr": _text(start_date),
        "endStr": _text(end_date),
        "singlefleetCdArray": "",
        "chnDescArray1": "",
        "page": "1",
        "currentStr": timestamp or str(time.time_ns()),
    }


def _headers(root: Tag) -> list[str]:
    for selector in ("thead th", ".hDiv th", "tr th"):
        values = [_text(cell.get_text(" ", strip=True)) for cell in root.select(selector)]
        if values and any(values):
            normalized = [value or ("选择" if index == 0 else f"列{index + 1}") for index, value in enumerate(values)]
            if len(set(normalized)) != len(normalized):
                raise IebContractError("飞行经历结果表存在重复表头")
            return normalized
    return []


def _rows(root: Tag, headers: list[str]) -> list[dict[str, str]]:
    nodes: list[Tag] = []
    for selector in (".bDiv tbody tr", "tbody.list tr", "tbody tr"):
        nodes = list(root.select(selector))
        if nodes:
            break
    rows: list[dict[str, str]] = []
    for node in nodes:
        values = [
            _text(cell.get("title") or cell.get_text(" ", strip=True))
            for cell in node.find_all("td", recursive=False)
        ]
        if not values or "没有相关信息" in " ".join(values):
            continue
        if len(values) == len(headers) + 1 and values[0].isdigit():
            values = values[1:]
        if len(values) != len(headers):
            raise IebContractError("飞行经历结果表表头和数据列数不一致")
        rows.append(dict(zip(headers, values)))
    return rows


def parse_result_table(
    html: str,
    expected_staff_number: str,
    expected_name: str = "",
) -> tuple[list[str], dict[str, str]]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    expected_name = _text(expected_name)
    for table in soup.select("table"):
        headers = _headers(table)
        if "员工号" not in headers:
            continue
        rows = _rows(table, headers)
        matches = [row for row in rows if row.get("员工号") == expected_staff_number]
        if len(matches) > 1:
            raise IebContractError("飞行经历结果无法按员工号唯一归属")
        if not matches:
            continue
        if expected_name and matches[0].get("姓名", "") != expected_name:
            raise IebContractError("姓名不匹配：页面返回人员与输入姓名不一致")
        return headers, matches[0]
    raise IebContractError("员工号不匹配：飞行经历结果中未找到当前查询人员")
