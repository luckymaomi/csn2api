"""SOC 工作台输入模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputPayload:
    input_mode: str = "excel"
    excel_name: str = ""
    excel_bytes: bytes | None = None
    pasted_text: str = ""
    common_remark: str = ""
