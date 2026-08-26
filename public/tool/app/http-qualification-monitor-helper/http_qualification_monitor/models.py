from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class ExportSummary:
    total: int
    success: int
    failed: int
    files: dict[str, Path] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    archive: Path | None = None
    interrupted: bool = False
    session_expired: bool = False


__all__ = ["ExportSummary"]
