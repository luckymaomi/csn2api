from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from ieb_protocol.roster_models import PersonQualification


HEADERS = ["序号", "员工号", "姓名", "资质类别"]


class RosterWorkbook:
    def __init__(self, target: Path) -> None:
        self.target = target
        self._relations: list[PersonQualification] = []
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self._save()

    @property
    def relations(self) -> list[PersonQualification]:
        return list(self._relations)

    def append_qualification(self, code: str, relations: list[PersonQualification]) -> list[PersonQualification]:
        added: list[PersonQualification] = []
        for relation in relations:
            normalized = PersonQualification(relation.staff_number, relation.name, code)
            self._relations.append(normalized)
            added.append(normalized)
        self._save()
        return added

    def _save(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "运行资质人员名册"
        sheet.append(HEADERS)
        for index, relation in enumerate(self._relations, start=1):
            sheet.append([index, relation.staff_number, relation.name, relation.qualification_code])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:D{max(1, sheet.max_row)}"
        sheet.column_dimensions["A"].width = 10
        sheet.column_dimensions["B"].width = 16
        sheet.column_dimensions["C"].width = 18
        sheet.column_dimensions["D"].width = 18
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="44546A")
            cell.alignment = Alignment(horizontal="center")
        for row in sheet.iter_rows(min_row=2, min_col=2, max_col=2):
            row[0].number_format = "@"
        temporary = self.target.with_name(f".{self.target.name}.tmp.xlsx")
        workbook.save(temporary)
        temporary.replace(self.target)

    def read_rows(self) -> list[list[object]]:
        workbook = load_workbook(self.target, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            return [list(row) for row in sheet.iter_rows(min_row=2, values_only=True)]
        finally:
            workbook.close()
