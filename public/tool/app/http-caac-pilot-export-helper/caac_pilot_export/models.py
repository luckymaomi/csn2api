from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PilotRecord:
    index: int
    listing: dict[str, Any]

    @property
    def pilot_id(self) -> str:
        return str(self.listing.get("pilotId") or "").strip()

    @property
    def name(self) -> str:
        return str(self.listing.get("pilotname") or self.listing.get("nameCn") or "").strip()


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
