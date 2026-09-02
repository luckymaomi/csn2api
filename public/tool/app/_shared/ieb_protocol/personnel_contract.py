from __future__ import annotations

import re
import time
from typing import Any, Callable

from bs4 import BeautifulSoup, Tag

from .base import IebContractError


TECHNICAL_HEADERS = [
    "#", "技术等级代码", "技术等级", "水平等级", "机型", "生效时间", "失效时间", "对应检查记录", "数据来源",
]
OPERATION_HEADERS = ["类型", "运行资格代码", "运行资格", "水平等级", "机型", "生效时间", "失效时间", "备注"]
TRAINING_RECORD_HEADERS = [
    "选择", "培训科目", "培训机型", "培训课时", "培训地点", "经办人", "教员",
    "培训时间", "培训結束时间", "训练结果", "考试成绩", "上传",
]
TRAINING_EXPERIENCE_HEADERS = [
    "全选", "序号", "训练日期", "训练机型", "训练科目", "类型", "检查单",
    "结论", "上传", "审批过程", "证书下载",
]
BASIC_INFO_FIELDS = [
    ("出生日期", "birthDate"), ("出生地", "birthPlace"), ("籍贯", "nativePlace"),
    ("国籍", "nationality"), ("民族", "nation"), ("户籍地", "residence"),
    ("户口性质", "typeOfResidence"), ("参加工作", "dateOfWork"), ("工作单位", "orgUnitId"),
    ("进入南航时间", "dateOfHire"), ("工作岗位", "position"), ("职务级别", "appointRank"),
    ("合同到期", "enddate"), ("空勤资格", "qualification"), ("用工类型", "statusType"),
    ("政治面貌", "politicalStand"), ("入党时间", "partydate"), ("健康状况", "health"),
    ("婚姻状况", "marrigeStatus"), ("身份证号", "identityNum"), ("手机号码", "mobile"),
]
SECTION_FIELDS = {
    "教育经历": [("学校", "school"), ("开始时间", "beginDate"), ("结束时间", "endDate"), ("学历", "education"), ("专业", "major"), ("学习方式", "studymode")],
    "工作经历": [("部门", "workDept"), ("开始时间", "beginDate"), ("结束时间", "endDate"), ("岗位", "workPost")],
    "职称信息": [("职称名称", "techposttitle"), ("开始时间", "beginDate"), ("结束时间", "endDate"), ("职称等级", "titlerank"), ("获得成就", "achive")],
    "家庭信息": [("姓名", "memName"), ("与本人关系", "memRelation"), ("出生日期", "memBirthday"), ("政治面貌", "politics"), ("工作单位", "memCorp"), ("职务", "memJob")],
}
INTERACTIVE_TITLE_TAGS = {"a", "button", "input", "select", "textarea"}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _cell_text(cell: Tag) -> str:
    own_title = _text(cell.get("title"))
    if own_title:
        return own_title
    for titled in cell.select("[title]"):
        if titled.name not in INTERACTIVE_TITLE_TAGS:
            nested_title = _text(titled.get("title"))
            if nested_title:
                return nested_title
    return _text(cell.get_text(" ", strip=True))


def _expanded_rows(table: Tag, cell_name: str, expected_columns: int = 0) -> list[list[str]]:
    active: dict[int, tuple[str, int]] = {}
    parsed: list[list[str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all(cell_name, recursive=False)
        if not cells:
            continue
        values: list[str] = []
        column = 0

        def consume_active() -> None:
            nonlocal column
            value, rows_left = active[column]
            values.append(value)
            if rows_left <= 1:
                del active[column]
            else:
                active[column] = (value, rows_left - 1)
            column += 1

        for cell in cells:
            while column in active:
                consume_active()
            value = _cell_text(cell)
            try:
                rowspan = max(1, int(cell.get("rowspan") or 1))
                colspan = max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError) as error:
                raise IebContractError("门户表格合并单元格参数异常") from error
            for offset in range(colspan):
                values.append(value)
                if rowspan > 1:
                    active[column + offset] = (value, rowspan - 1)
            column += colspan
        limit = expected_columns or max([column, *(key + 1 for key in active)], default=column)
        while column < limit:
            if column in active:
                consume_active()
            else:
                values.append("")
                column += 1
        parsed.append(values)
    return parsed


def _table_data(root: Tag) -> tuple[list[str], list[dict[str, str]]]:
    tables = list(root.find_all("table"))
    header_table = next((table for table in tables if table.find("th") is not None), None)
    if header_table is None:
        return [], []
    header_rows = _expanded_rows(header_table, "th")
    headers = header_rows[0] if header_rows else []
    headers = [value or ("选择" if index == 0 else f"列{index + 1}") for index, value in enumerate(headers)]
    if not headers:
        return [], []
    if len(set(headers)) != len(headers):
        raise IebContractError("门户表格存在重复表头")
    data_table = next((table for table in tables if table.find("td") is not None), None)
    if data_table is None:
        return headers, []
    rows: list[dict[str, str]] = []
    for values in _expanded_rows(data_table, "td", len(headers)):
        row_text = " | ".join(value for value in values if value)
        if not row_text or "没有相关信息" in row_text:
            continue
        if len(values) != len(headers):
            raise IebContractError("门户表格表头与数据列数不一致")
        rows.append(dict(zip(headers, values)))
    return headers, rows


def parse_employee_identity(html: str, employee_id: str, expected_name: str = "") -> dict[str, str]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    candidates: list[dict[str, str]] = []
    for root in list(soup.select(".flexigrid")) or [soup]:
        headers, rows = _table_data(root)
        if "员工号" in headers and "姓名" in headers:
            candidates.extend(row for row in rows if row.get("员工号") == employee_id)
    if len(candidates) != 1:
        raise IebContractError("人员检索结果无法按员工号唯一归属")
    page_name = _text(candidates[0].get("姓名"))
    if not page_name:
        raise IebContractError("人员检索结果缺少姓名")
    normalized_expected = re.sub(r"\s+", "", re.sub(r"[（(][^）)]*[）)]", "", expected_name))
    normalized_actual = re.sub(r"\s+", "", re.sub(r"[（(][^）)]*[）)]", "", page_name))
    if expected_name and normalized_expected != normalized_actual:
        raise IebContractError("姓名不匹配：页面返回人员与输入姓名不一致")
    return {"employeeId": employee_id, "name": page_name}


def parse_detail_table(html: str, selector: str, expected_headers: list[str] | None = None) -> list[dict[str, str]]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    root = soup.select_one(selector)
    if root is None:
        raise IebContractError(f"门户响应缺少结果区域 {selector}")
    headers, rows = _table_data(root)
    if not headers:
        raise IebContractError(f"门户响应的结果区域 {selector} 缺少表头")
    if expected_headers is not None and headers != expected_headers:
        raise IebContractError(f"门户响应的结果区域 {selector} 表头异常：{headers}")
    return rows


def _mapped_rows(payload: object, fields: list[tuple[str, str]], section: str) -> list[dict[str, str]]:
    if payload is None:
        return []
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise IebContractError(f"门户基础信息的{section}结构异常")
    return [{label: _text(item.get(source)) for label, source in fields} for item in payload]


def parse_basic_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("empDto"), dict):
        raise IebContractError("门户基础信息响应结构异常")
    employee = payload["empDto"]
    return {
        "基本信息": {label: _text(employee.get(source)) for label, source in BASIC_INFO_FIELDS},
        **{
            section: _mapped_rows(payload.get(source), SECTION_FIELDS[section], section)
            for section, source in (
                ("教育经历", "eduList"),
                ("工作经历", "workList"),
                ("职称信息", "titleList"),
                ("家庭信息", "relationList"),
            )
        },
    }


def parse_training_record_pages(fetch_page: Callable[[int], str]) -> list[dict[str, str]]:
    first_html = str(fetch_page(1) or "")
    pages = [int(value) for value in re.findall(r"goPageTwo\([^)]*['\"](\d+)['\"]\s*,\s*true\)", first_html)]
    last_page = max(pages, default=1)
    rows: list[dict[str, str]] = []
    for page in range(1, last_page + 1):
        html = first_html if page == 1 else str(fetch_page(page) or "")
        page_rows = parse_detail_table(html, "#showTrainingRecordListDiv", TRAINING_RECORD_HEADERS)
        rows.extend({**row, "来源页码": str(page)} for row in page_rows)
    return rows


def build_employee_query_params(employee_id: str, current_str: str | None = None) -> list[tuple[str, str]]:
    return [
        ("personName", employee_id), ("staffNumAllDesc", ""), ("primaryBaseArray", ""),
        ("baseArray", ""), ("techBase", ""), ("bolMultiQualCd", ""),
        ("bolPriBase", ""), ("bolJCY", ""), ("activeStatusArray", "ZAIZHI"),
        ("activeStatusArray", "WAIBU"), ("activeStatusArray", "TUIXIU"),
        ("activeStatusArray", "LIZHI"), ("fleetCdbranch", ""), ("isOperQual", "Y"),
        ("operQualArray", ""), ("page", "1"),
        ("currentStr", current_str or str(int(time.time() * 1000))),
    ]
