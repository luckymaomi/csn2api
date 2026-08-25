from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-caac-pilot-export-helper"
sys.path.insert(0, str(ROOT))

from caac_pilot_export.credentials import parse_credentials  # noqa: E402
from caac_pilot_export.exporter import ResultExporter  # noqa: E402
from caac_pilot_export.models import PilotOutcome, PilotRecord  # noqa: E402
from caac_pilot_export.portal_client import PortalClient, PortalContractError, PortalSessionExpired  # noqa: E402
from caac_pilot_export.runner import BatchRunner  # noqa: E402


class CoreTests(unittest.TestCase):
    def test_shell_cookie_escape_is_decoded(self) -> None:
        cookies = parse_credentials(r"-b $'yzzzm=a; JSESSIONID=abc\u0021xyz; home=h\_1'")
        self.assertEqual(cookies["JSESSIONID"], "abc!xyz")
        self.assertEqual(cookies["home"], "h_1")

    def test_page_parser_requires_total_and_rows(self) -> None:
        rows, total = PortalClient._parse_page({"total": 2, "rows": [{"pilotId": "1"}]})
        self.assertEqual((len(rows), total), (1, 2))
        with self.assertRaises(PortalContractError):
            PortalClient._parse_page({"rows": []})

    def test_runner_continues_after_one_detail_failure(self) -> None:
        records = [PilotRecord(i, {"pilotId": str(i + 1), "pilotname": f"P{i + 1}"}) for i in range(3)]
        portal = Mock()
        portal.query_one.side_effect = [RuntimeError("普通错误"), PilotOutcome(records[1], "成功", {"pilotId": "2"}), PilotOutcome(records[2], "成功", {"pilotId": "3"})]
        persisted = []
        result = BatchRunner(portal, persist=persisted.append).run(records, 3)
        self.assertEqual([item.status for item in result.outcomes], ["失败", "成功", "成功"])
        self.assertEqual(portal.query_one.call_count, 3)
        self.assertEqual([item.status for item in persisted], ["失败", "成功", "成功"])

    def test_runner_stops_after_session_expired(self) -> None:
        records = [PilotRecord(i, {"pilotId": str(i + 1)}) for i in range(2)]
        portal = Mock()
        portal.query_one.side_effect = PortalSessionExpired("expired")
        result = BatchRunner(portal).run(records, 2)
        self.assertEqual(result.outcomes[0].status, "失败")
        self.assertEqual(result.outcomes[1].status, "未查询")
        self.assertTrue(result.session_expired)
        self.assertEqual(portal.query_one.call_count, 1)

    def test_exporter_writes_one_sheet_and_dynamic_columns(self) -> None:
        outcome = PilotOutcome(PilotRecord(0, {"pilotId": "1", "pilotname": "示例"}), "成功", {"pilotId": "1", "pilotPhotoFileUrl": None, "layerInfosList": [{"layerinfo": "根", "sublayers": [{"layerinfo": "子", "sublayers": []}]}], "educationList": [{"school": "学校"}]})
        with tempfile.TemporaryDirectory() as directory:
            path = ResultExporter(Path(directory), "run").write([outcome])
            workbook = load_workbook(path)
            self.assertEqual(workbook.sheetnames, ["飞行员信息"])
            headers = [cell.value for cell in workbook.active[1]]
            self.assertIn("详情.layerInfosList.资质层级", headers)
            self.assertIn("详情.educationList", headers)
            self.assertIn("根\n  子", [cell.value for cell in workbook.active[2]])

    def test_exporter_saves_each_completed_pilot_as_checkpoint(self) -> None:
        first = PilotOutcome(PilotRecord(0, {"pilotId": "1"}), "成功", {"pilotId": "1", "firstField": "A"})
        second = PilotOutcome(PilotRecord(1, {"pilotId": "2"}), "成功", {"pilotId": "2", "laterField": "B"})
        with tempfile.TemporaryDirectory() as directory:
            exporter = ResultExporter(Path(directory), "checkpoint")
            path = exporter.append(first)
            first_book = load_workbook(path)
            self.assertEqual(first_book.active.max_row, 2)
            exporter.append(second)
            second_book = load_workbook(path)
            self.assertEqual(second_book.active.max_row, 3)
            self.assertIn("详情.laterField", [cell.value for cell in second_book.active[1]])

    def test_epoch_milliseconds_and_deep_qualification_tree_are_readable(self) -> None:
        from caac_pilot_export.flatten import flatten_detail
        flattened = flatten_detail({"birthday": 297014400000, "layerInfosList": [{"layerinfo": "根", "sublayers": [{"layerinfo": "子", "sublayers": [{"layerinfo": "孙", "sublayers": []}]}]}]})
        self.assertEqual(flattened["详情.birthday"], "1979-06-01")
        self.assertEqual(flattened["详情.layerInfosList.资质层级"], "根\n  子\n    孙")


if __name__ == "__main__":
    unittest.main()
