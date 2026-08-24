import tempfile
import threading
import unittest
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-soc-positioning-helper"
sys.path.insert(0, str(APP_ROOT))

from soc_positioning.models import FlightOption, StaffIdentity, SubmitOutcome  # noqa: E402
from soc_positioning.portal_client import PortalError, PortalSessionExpired  # noqa: E402
from soc_positioning.result_store import ResultStore  # noqa: E402
from soc_positioning.runner import BatchRunner  # noqa: E402


OPTION = FlightOption("CZ1234", "1234", "01", "2026-01-15", "CANCSX", "0800-1000", "", "32A", "CZ", "composite")
RECORDS = [
    {"来源行": 2, "员工号": "000001", "姓名": "测试一", "航班日期": "2026-01-15", "出发地": "广州", "目的地": "长沙", "航班号": "CZ1234", "申请原因": "学习培训", "申请原因代码": "6", "备注": ""},
    {"来源行": 3, "员工号": "000002", "姓名": "测试二", "航班日期": "2026-01-15", "出发地": "广州", "目的地": "长沙", "航班号": "CZ1234", "申请原因": "学习培训", "申请原因代码": "6", "备注": ""},
]


class FakeBatchClient:
    def __init__(self, first_error: Exception | None = None):
        self.first_error = first_error
        self.calls = 0

    def list_flights(self, *_args):
        self.calls += 1
        if self.first_error is not None and self.calls == 1:
            raise self.first_error
        return [OPTION]

    def choose_flight(self, options, _requested):
        return options[0]

    def validate_staff(self, record, _option):
        return StaffIdentity(str(record["员工号"]), str(record["姓名"]), "")

    def submit(self, _record, _option, _identity):
        return SubmitOutcome(True, "录入成功！")


class SocRunnerTests(unittest.TestCase):
    def test_row_error_is_recorded_and_next_row_continues(self):
        client = FakeBatchClient(PortalError("业务拒绝"))
        with tempfile.TemporaryDirectory() as directory:
            store = ResultStore(Path(directory), "run")
            summary = BatchRunner(client, store, threading.Event()).run(RECORDS)
            store.close()
            self.assertEqual(summary["completed"], 2)
            self.assertEqual(summary["success"], 1)
            self.assertEqual(summary["failed"], 1)

    def test_session_expiry_stops_without_processing_next_row(self):
        client = FakeBatchClient(PortalSessionExpired("会话失效"))
        with tempfile.TemporaryDirectory() as directory:
            store = ResultStore(Path(directory), "run")
            with self.assertRaises(PortalSessionExpired):
                BatchRunner(client, store, threading.Event()).run(RECORDS)
            store.close()
            self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
