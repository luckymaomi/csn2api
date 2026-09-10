from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ieb_protocol.training_arrangement_models import TrainingOption, TrainingWindow


@dataclass(frozen=True)
class QueryInput:
    category: str
    date_range: str
    end_date: date


@dataclass(frozen=True)
class QueryResult:
    windows: list[TrainingWindow]
    interrupted: bool = False
    session_expired: bool = False


@dataclass(frozen=True)
class AreaWindow:
    category: str
    key: str
    label: str
    start: date
    end: date
    headers: list[str]
    rows: list[dict[str, str]]
    pages: int
    total: int | None


@dataclass(frozen=True)
class AreaQueryResult:
    windows: list[AreaWindow]
    summary: list[dict[str, object]]
    interrupted: bool = False
    session_expired: bool = False


Event = dict[str, Any]

__all__ = ["AreaQueryResult", "AreaWindow", "QueryInput", "QueryResult", "TrainingOption", "TrainingWindow", "Event"]
