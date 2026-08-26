from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QualificationItem:
    name: str
    code: str


@dataclass(frozen=True)
class QualificationGroup:
    name: str
    code: str
    items: list[QualificationItem] = field(default_factory=list)


@dataclass(frozen=True)
class QualificationPage:
    rows: list[dict[str, Any]]
    total: int
    pages: int
    page_number: int
    page_size: int
    has_next_page: bool

    @property
    def columns(self) -> list[str]:
        columns: list[str] = []
        for row in self.rows:
            for name in row:
                text = str(name)
                if text not in columns:
                    columns.append(text)
        return columns
