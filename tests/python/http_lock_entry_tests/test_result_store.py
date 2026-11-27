from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from .common import APP_DIR  # noqa: F401
from http_lock_entry.result_store import RESULT_HEADERS, ResultStore


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

    def test_result_headers_group_input_left_portal_right(self):
        labels = [label for label, _key in RESULT_HEADERS]
        self.assertEqual(
            labels,
            [
                "序号",
                "来源行",
                "员工号",
                "输入姓名",
                "输入锁班类型",
                "输入开始日期",
                "输入结束日期",
                "锁班备注",
                "门户姓名",
                "实际锁班类型",
                "实际开始日期时间",
                "实际结束日期时间",
                "时间模式",
                "处理状态",
                "门户结果",
                "冲突原因",
                "说明",
                "记录时间",
            ],
        )
        self.assertLess(labels.index("锁班备注"), labels.index("门户姓名"))
        self.assertLess(labels.index("输入结束日期"), labels.index("实际开始日期时间"))


if __name__ == "__main__":
    unittest.main()
