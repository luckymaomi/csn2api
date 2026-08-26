from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from .common import APP_DIR  # noqa: F401
from http_lock_entry.result_store import ResultStore


class HttpLockEntryResultStoreTest(unittest.TestCase):
    def test_conflict_reason_has_an_independent_excel_column(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResultStore(Path(directory), "conflict")
            store.append({
                "index": 1,
                "employeeId": "900001",
                "status": "冲突",
                "portalStatus": "冲突",
                "conflictReason": "年度年假锁班天数不足",
                "message": "",
            })

            workbook = load_workbook(store.path, data_only=True)
            headers = [cell.value for cell in workbook["录入结果"][1]]
            values = [cell.value for cell in workbook["录入结果"][2]]
            row = dict(zip(headers, values))
            self.assertEqual(row["冲突原因"], "年度年假锁班天数不足")
            self.assertIsNone(row["说明"])
            workbook.close()


if __name__ == "__main__":
    unittest.main()
