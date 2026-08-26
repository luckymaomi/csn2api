"""锁班 APP 编排输入模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputPayload:
    input_mode: str
    excel_name: str = ""
    excel_bytes: bytes | None = None
    pasted_text: str = ""
    whitelist_text: str = ""
    common_reason: str = ""
    approve_after_submit: bool = False
