from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockTypeMetadata:
    code: str
    label: str
    description: str
    limit_flag: str
    date_split_flag: str

    @property
    def supports_monthly(self) -> bool:
        return self.limit_flag != "1" and self.code not in {"ALV_FD", "CRM"}

    @property
    def default_start_time(self) -> str:
        return "08:30" if self.code == "CRM" else "08:59"

    @property
    def default_end_time(self) -> str:
        return "16:30" if self.code == "CRM" else "19:59"


@dataclass(frozen=True)
class PortalMetadata:
    lock_types: dict[str, LockTypeMetadata]
    default_reason_prefix: str


@dataclass(frozen=True)
class EmployeeIdentity:
    employee_id: str
    name: str
    department: str


@dataclass(frozen=True)
class LockSubmission:
    employee_id: str
    lock_type: str
    time_mode: int
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    month: str
    days: tuple[int, ...]
    reason: str

    def expected_ranges(self) -> list[tuple[str, str]]:
        if self.time_mode == 1:
            return [(f"{self.start_date} {self.start_time}", f"{self.end_date} {self.end_time}")]
        return [
            (f"{self.month}-{day:02d} {self.start_time}", f"{self.month}-{day:02d} {self.end_time}")
            for day in self.days
        ]


@dataclass(frozen=True)
class SubmitResult:
    result_rows: list[dict[str, str]]
    conflict_rows: list[dict[str, str]]
