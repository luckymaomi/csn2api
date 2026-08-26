from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PilotRecord:
    index: int
    listing: dict[str, Any]
    input_name: str = ""
    input_archive_no: str = ""
    source: str = ""
    input_error: str = ""
    input_row: int = 0

    @property
    def pilot_id(self) -> str:
        return str(self.listing.get("pilotId") or "").strip()

    @property
    def name(self) -> str:
        return str(self.listing.get("pilotname") or self.listing.get("nameCn") or self.input_name or "").strip()

    @property
    def archive_no(self) -> str:
        return str(self.listing.get("archiveNo") or self.input_archive_no or "").strip()


@dataclass(frozen=True)
class InputIssue:
    input_row: int
    name: str
    archive_no: str
    message: str
    source: str

    def __str__(self) -> str:
        return f"{self.source}：{self.message}"


@dataclass(frozen=True)
class InputPayload:
    excel_name: str = ""
    excel_bytes: bytes | None = None


@dataclass
class PilotOutcome:
    record: PilotRecord
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class BatchResult:
    outcomes: list[PilotOutcome]
    total: int
    stopped: bool = False
    session_expired: bool = False

    @property
    def success(self) -> int:
        return sum(outcome.status == "成功" for outcome in self.outcomes)

    @property
    def failed(self) -> int:
        return sum(outcome.status != "成功" for outcome in self.outcomes)
