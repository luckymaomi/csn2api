from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from .common import APP_ROOT  # noqa: F401
from http_flight_detail.input_data import normalize_month, parse_pasted_records, read_excel_records


class InputDataTests(unittest.TestCase):
    def test_normalizes_supported_month_values(self) -> None:
        self.assertEqual(normalize_month("2026/1"), "2026-01")
        self.assertEqual(normalize_month("2023/05"), "2023-05")
        self.assertEqual(normalize_month(date(2024, 4, 20)), "2024-04")

    def test_rejects_unapproved_or_invalid_month_text(self) -> None:
        for value in ("2026-01", "2026/13", "26/1", "2026/1/1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_month(value)

    def test_reads_exact_four_column_excel_and_rejects_duplicate_employee(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["员工号", "姓名", "开始年月", "结束年月"])
            sheet.append([900001, "示例甲", "2026/1", "2026/10"])
            sheet.append([900001, "示例甲", "2026/2", "2026/3"])
            workbook.save(path)
            workbook.close()

            records, errors = read_excel_records(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].start_month, "2026-01")
        self.assertEqual(records[0].end_month, "2026-10")
        self.assertIn("重复员工号", errors[0])

    def test_pasted_table_requires_header_and_preserves_range(self) -> None:
        records, errors = parse_pasted_records(
            "员工号\t姓名\t开始年月\t结束年月\n900002\t示例乙\t2023/05\t2026/08"
        )

        self.assertEqual(errors, [])
        self.assertEqual(records[0].months()[0], "2023-05")
        self.assertEqual(records[0].months()[-1], "2026-08")
        self.assertEqual(len(records[0].months()), 40)

    def test_rejects_missing_or_extra_headers_and_reverse_range(self) -> None:
        for text in (
            "员工号\t姓名\t开始年月\n900001\t示例甲\t2026/1",
            "员工号\t姓名\t开始年月\t结束年月\t备注\n900001\t示例甲\t2026/1\t2026/2\t测试",
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "表头"):
                parse_pasted_records(text)

        records, errors = parse_pasted_records(
            "员工号,姓名,开始年月,结束年月\n900001,示例甲,2026/8,2026/1"
        )
        self.assertEqual(records, [])
        self.assertIn("结束年月早于开始年月", errors[0])


if __name__ == "__main__":
    unittest.main()
