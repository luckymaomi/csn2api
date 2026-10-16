from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import IebContractError
from .flight_detail_contract import _cell_value, parse_timeline


def is_summary_label(value: str) -> bool:
    return re.fullmatch(r'汇总(?:\s*\(\s*外航经历\s*\))?', value.strip()) is not None


def parse_history(html: str, staff_number: str, name: str) -> tuple[list[str], list[dict[str, str]]]:
    """校验人员归属和唯一表格，保留时间轴全页行列与原顺序。"""
    entries = parse_timeline(html, staff_number, name)
    soup = BeautifulSoup(html, 'html.parser')
    buttons = [node for node in soup.select('[onclick]') if str(node.get('onclick', '')).strip().startswith('showflyTimeDetail(')]
    if len(entries) != len(buttons):
        raise IebContractError('飞行经历时间人员归属不唯一')
    header_rows = []
    summary_rows = []
    data_tables = []
    for row in soup.select('table tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        values = [_cell_value(cell) for cell in cells]
        if '日期' in values and '飞行时间' in values:
            header_rows.append(values)
        if values and is_summary_label(values[0]):
            summary_rows.append(values)
            data_tables.append(row.find_parent('table'))
    if len(header_rows) != 1 or len(summary_rows) != 1:
        raise IebContractError('飞行经历时间表头或汇总行缺失或不唯一')
    headers = header_rows[0]
    if not all(headers) or len(headers) != len(set(headers)):
        raise IebContractError('飞行经历时间表头为空或重复')
    results = []
    for row in data_tables[0].select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        if not cells:
            continue
        values = [_cell_value(cell) for cell in cells]
        if values == headers:
            continue
        if len(headers) != len(values):
            raise IebContractError('飞行经历时间表头和数据列数不一致')
        results.append(dict(zip(headers, values)))
    return headers, results
