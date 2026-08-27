from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

from openpyxl import Workbook


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "http-qualification-roster-helper"
SHARED_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "_shared"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))


PORTAL_PERSON_HEADERS = [
    "员工号", "姓名", "技术基地", "注册基地", "运行基地", "技术信息", "实际机型", "保护等级",
    "性别", "在职状态", "出生日期", "国籍", "政治面貌", "所属部门", "行政职务", "行政级别",
]


def person_row(staff_number: str = "000123", name: str = "测试甲", base: str = "广州") -> dict[str, str]:
    return {
        "员工号": staff_number,
        "姓名": name,
        "技术基地": base,
        "注册基地": base,
        "运行基地": base,
        "技术信息": "机长",
        "实际机型": "B777",
        "保护等级": "A",
        "性别": "男",
        "在职状态": "在职",
        "出生日期": "1980-01-02",
        "国籍": "中国",
        "政治面貌": "群众",
        "所属部门": "测试部门",
        "行政职务": "",
        "行政级别": "",
    }


def portal_export_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet0"
    export_headers = [
        "员工号", "姓名", "技术基地", "注册基地", "运行基地", "技术信息", "实际机型", "保护等级",
        "运行资格", "总经历数时间", "总起落数", "检查员资格", "性别", "在职状态", "分部",
        "出生日期", "国籍", "政治面貌", "所属部门", "行政职务", "行政级别",
    ]
    sheet.append(export_headers)
    for values in (person_row(), person_row("000456", "测试乙", "深圳")):
        enriched = {**values, "运行资格": "门户其他字段", "总经历数时间": "1000:00", "总起落数": "200", "检查员资格": "", "分部": ""}
        sheet.append([enriched.get(header, "") for header in export_headers])
    raw = io.BytesIO()
    workbook.save(raw)
    source = zipfile.ZipFile(io.BytesIO(raw.getvalue()))
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<dimension ref="A1:U3"/>', b'<dimension ref="A1"/>')
            target.writestr(item, content)
    return output.getvalue()
