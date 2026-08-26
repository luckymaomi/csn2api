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


def portal_export_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet0"
    sheet.append(["员工号", "姓名", "运行基地", "运行资格"])
    sheet.append(["000123", "测试甲", "广州", "门户其他字段"])
    sheet.append(["000456", "测试乙", "深圳", "门户其他字段"])
    raw = io.BytesIO()
    workbook.save(raw)
    source = zipfile.ZipFile(io.BytesIO(raw.getvalue()))
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<dimension ref="A1:D3"/>', b'<dimension ref="A1"/>')
            target.writestr(item, content)
    return output.getvalue()
