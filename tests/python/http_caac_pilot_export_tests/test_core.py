from __future__ import annotations

import sys
import tempfile
import threading
import unittest
import urllib.request
from html.parser import HTMLParser
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
from caac_pilot_export.server import create_server  # noqa: E402


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value and value.startswith("./"):
                self.paths.append("/" + value[2:])


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
            self.assertIn("资质信息", headers)
            self.assertIn("教育经历", headers)
            self.assertNotIn("详情.pilotPhotoFileUrl", headers)
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
            self.assertIn("未映射字段（laterField）", [cell.value for cell in second_book.active[1]])

    def test_epoch_milliseconds_and_deep_qualification_tree_are_readable(self) -> None:
        from caac_pilot_export.flatten import flatten_detail
        flattened = flatten_detail({"birthday": 297014400000, "medicalBirthday": "1979-06-01", "licenseLimit": "第一条</br>第二条", "layerInfosList": [{"layerinfo": "根", "sublayers": [{"layerinfo": "子", "sublayers": [{"layerinfo": "孙", "sublayers": []}]}]}]})
        self.assertEqual(flattened["出生日期"], "1979-06-01")
        self.assertEqual(flattened["执照限制"], "第一条\n第二条")
        self.assertEqual(flattened["资质信息"], "根\n  子\n    孙")

    def test_detail_cleaner_translates_records_and_hides_internal_fields(self) -> None:
        from caac_pilot_export.flatten import flatten_detail

        flattened = flatten_detail({
            "printList": [
                {
                    "printId": "internal-print-id",
                    "licenseId": "internal-license-id",
                    "printReason": "英语语言等级更新",
                    "agreeUser": "SYS",
                    "agreeDate": 1778947200000,
                    "creationBy": "SYS",
                    "creationDate": 1778947200000,
                    "extraFlag": "保留",
                },
                {"printReason": "补发", "agreeDate": 1779033600000},
            ]
        })

        text = flattened["执照打印记录"]
        self.assertIn("打印原因：英语语言等级更新", text)
        self.assertIn("审批人：SYS", text)
        self.assertIn("审批日期：2026-05-17", text)
        self.assertIn("未映射字段（extraFlag）：保留", text)
        self.assertIn("\n2. 打印原因：补发", text)
        self.assertNotIn("printId", text)
        self.assertNotIn("licenseId", text)
        self.assertNotIn("creationBy", text)

    def test_detail_values_override_listing_values_without_duplicate_raw_headers(self) -> None:
        outcome = PilotOutcome(
            PilotRecord(0, {"pilotId": "1", "pilotname": "列表姓名", "listOnly": "列表值"}),
            "成功",
            {"pilotId": "1", "pilotname": "详情姓名", "detailOnly": "详情值"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = ResultExporter(Path(directory), "merge").write([outcome])
            workbook = load_workbook(path)
            headers = [cell.value for cell in workbook.active[1]]
            values = [cell.value for cell in workbook.active[2]]
            row = dict(zip(headers, values))
            self.assertEqual(row["姓名"], "详情姓名")
            self.assertEqual(row["未映射字段（listOnly）"], "列表值")
            self.assertEqual(row["未映射字段（detailOnly）"], "详情值")
            self.assertFalse(any(str(header).startswith(("列表.", "详情.")) for header in headers))

    def test_workbench_serves_every_local_ui_asset(self) -> None:
        manager = Mock()
        manager.snapshot.return_value = {"phase": "idle"}
        manager.download_path.return_value = None
        server = create_server(ROOT, 0, manager)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
                html = response.read().decode("utf-8")
            parser = _AssetParser()
            parser.feed(html)
            self.assertIn("/libs/bootstrap.min.css", parser.paths)
            for path in parser.paths:
                with self.subTest(path=path):
                    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=5) as response:
                        content_type = response.headers.get_content_type()
                        body = response.read()
                    self.assertGreater(len(body), 20)
                    if path.endswith(".css"):
                        self.assertEqual(content_type, "text/css")
                    elif path.endswith((".js", ".mjs")):
                        self.assertIn(content_type, {"text/javascript", "application/javascript"})
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
