from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "http-qualification-monitor-helper"
SHARED_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "_shared"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))


def ooxml_bytes(marker: str = "fixture") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        archive.writestr("xl/worksheets/sheet1.xml", f"<worksheet>{marker}</worksheet>")
    return stream.getvalue()


CLASSIFICATION_PAYLOAD = [
    {
        "id": "1",
        "msgType": "资质运行类",
        "msgCode": "ZZYX",
        "sonList": [
            {"msgType": "90天3起落", "msgCode": "90D3F"},
            {"msgType": "新岗位120天100小时", "msgCode": "120D100H"},
        ],
    },
    {
        "id": "2",
        "msgType": "资质资格类",
        "msgCode": "ZZZG",
        "sonList": [{"msgType": "ICAO4级", "msgCode": "ICAO4"}],
    },
    {
        "id": "3",
        "msgType": "资质特殊类",
        "msgCode": "ZZTS",
        "sonList": [{"msgType": "左座经历起落监控", "msgCode": "ZZJLQL"}],
    },
]
