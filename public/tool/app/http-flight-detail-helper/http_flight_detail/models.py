from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryRecord:
    employee_id: str
    name: str
    start_month: str
    end_month: str
    source: str

    def months(self) -> list[str]:
        from ieb_protocol.flight_detail_contract import month_range
        return month_range(self.start_month, self.end_month)


@dataclass(frozen=True)
class MonthOutcome:
    index: int
    record_index: int
    record: QueryRecord
    month: str
    status: str
    rows: list[dict[str, str]] | None = None
    headers: list[str] | None = None
    error: str = ""


@dataclass(frozen=True)
class BatchResult:
    outcomes: list[MonthOutcome]
    stopped: bool
    session_expired: bool

    @property
    def success(self) -> int:
        return sum(item.status == "成功" for item in self.outcomes)

    @property
    def failed(self) -> int:
        return sum(item.status == "失败" for item in self.outcomes)


@dataclass(frozen=True)
class InputPayload:
    input_mode: str
    excel_name: str = ""
    excel_bytes: bytes | None = None
    pasted_text: str = ""


Event = dict[str, Any]

