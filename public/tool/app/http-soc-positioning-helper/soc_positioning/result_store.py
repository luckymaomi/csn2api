"""Immediate, local-only Excel result storage."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


class ResultStore:
    def __init__(self, root: Path, run_id: str):
        self.directory = root / run_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / f"SOC随机置位结果_{run_id}.xlsx"
        self.workbook = Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "录入结果"
        self.sheet.append(["来源行", "员工号", "姓名", "日期", "出发地", "目的地", "航班号", "申请原因", "备注", "状态", "说明"])
        self._save()

    def append(self, row: dict[str, object]) -> None:
        self.sheet.append([
            row.get("来源行", ""), row.get("员工号", ""), row.get("姓名", ""), row.get("航班日期", ""),
            row.get("出发地", ""), row.get("目的地", ""), row.get("航班号", ""), row.get("申请原因", ""),
            row.get("备注", ""), row.get("状态", ""), row.get("说明", ""),
        ])
        self._save()

    def _save(self) -> None:
        self.workbook.save(self.path)

    def close(self) -> None:
        self.workbook.close()
