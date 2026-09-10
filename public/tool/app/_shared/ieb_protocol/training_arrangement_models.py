from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TrainingOption:
    value: str
    label: str


@dataclass(frozen=True)
class TrainingPage:
    headers: list[str]
    rows: list[dict[str, str]]
    page: int
    total: int | None


@dataclass(frozen=True)
class TrainingWindow:
    key: str
    label: str
    start: date
    end: date
    headers: list[str]
    rows: list[dict[str, str]]
    pages: int
    total: int | None
