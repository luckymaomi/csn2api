from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .common import APP_ROOT  # noqa: F401
except ImportError:
    from common import APP_ROOT  # type: ignore[no-redef]  # noqa: F401

from http_qualification_roster.exporter import RosterWorkbook
from ieb_protocol.roster_models import OperatingQualification, PortalPerson, QueryFilters
from http_qualification_roster.portal_client import PortalSessionExpired
from http_qualification_roster.runner import RosterRunner


QUALIFICATIONS = [
    OperatingQualification("RAMA", "北美区域单飞资格"),
    OperatingQualification("EAMA", "样例资格"),
    OperatingQualification("RANC", "样例资格二"),
]


class RecordingClient:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[tuple[str, str]] = []

    def query_count(self, _filters: QueryFilters, code: str) -> int:
        self.calls.append(("query", code))
        if code in self.failures:
            raise self.failures[code]
        return 1

    def export_people(self, _filters: QueryFilters, code: str) -> list[PortalPerson]:
        self.calls.append(("export", code))
        return [PortalPerson("000123", "测试甲")]


class RosterRunnerTests(unittest.TestCase):
    def test_item_failure_is_recorded_and_later_qualification_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = RecordingClient({"EAMA": RuntimeError("虚构失败")})
            workbook = RosterWorkbook(Path(directory) / "result.xlsx")
            events: list[dict[str, object]] = []
            summary = RosterRunner(client, workbook, events.append).run(QueryFilters(), QUALIFICATIONS)
            self.assertEqual(client.calls, [
                ("query", "RAMA"), ("export", "RAMA"),
                ("query", "EAMA"),
                ("query", "RANC"), ("export", "RANC"),
            ])
            self.assertEqual((summary.success, summary.failed, summary.relationship_count), (2, 1, 2))
            self.assertEqual([row[3] for row in workbook.read_rows()], ["RAMA", "RANC"])

    def test_session_expiry_stops_before_later_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = RecordingClient({"EAMA": PortalSessionExpired("会话失效")})
            summary = RosterRunner(
                client,
                RosterWorkbook(Path(directory) / "result.xlsx"),
                lambda _event: None,
            ).run(QueryFilters(), QUALIFICATIONS)
            self.assertEqual(client.calls, [("query", "RAMA"), ("export", "RAMA"), ("query", "EAMA")])
            self.assertTrue(summary.session_expired)


if __name__ == "__main__":
    unittest.main()
