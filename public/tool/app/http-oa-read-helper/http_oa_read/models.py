"""OA APP 批次结果模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatchResult:
    success: int
    failed: int
    skipped: int
    stopped: bool
    session_expired: bool
    error: str = ""
