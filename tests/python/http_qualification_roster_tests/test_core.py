from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .common import APP_ROOT, portal_export_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, portal_export_bytes  # type: ignore[no-redef]  # noqa: F401

from http_qualification_roster.exporter import RosterWorkbook
from ieb_protocol.roster_models import PersonQualification, QueryFilters
from http_qualification_roster.portal_client import (
    build_filter_params,
    parse_operating_qualifications,
    parse_personnel_export,
)


QUALIFICATION_HTML = """
<table>
  <thead><tr><th>选择</th><th>资格代码</th><th>中文描述</th><th>资格简码</th><th>资格类型</th><th>类型描述</th></tr></thead>
  <tbody>
    <tr><td><input type="checkbox" value="internal-1"></td><td class="qualCdTd" data-qualCd="RAMA">RAMA</td><td>北美区域单飞资格</td><td>RAMA</td><td>QYHXZG</td><td>区域航线资格</td></tr>
    <tr><td><input type="checkbox" value="internal-2"></td><td class="qualCdTd" data-qualCd="EAMA">EAMA</td><td>样例资格</td><td>EAMA</td><td>QYHXZG</td><td>区域航线资格</td></tr>
  </tbody>
</table>
"""


class QualificationRosterCoreTests(unittest.TestCase):
    def test_dynamic_qualification_parser_uses_query_code_not_checkbox_id(self) -> None:
        options = parse_operating_qualifications(QUALIFICATION_HTML)
        self.assertEqual([option.code for option in options], ["RAMA", "EAMA"])
        self.assertEqual(options[0].name, "北美区域单飞资格")
        self.assertNotIn("internal-1", [option.code for option in options])

    def test_filter_params_repeat_all_active_statuses_and_one_qualification(self) -> None:
        filters = QueryFilters(fleet_codes=["777"], active_statuses=["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"])
        params = build_filter_params(filters, "RAMA", page=1)
        self.assertEqual(
            [value for name, value in params if name == "activeStatusArray"],
            ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"],
        )
        self.assertEqual([value for name, value in params if name == "operQualArray"], ["RAMA"])
        self.assertEqual([value for name, value in params if name == "fleetCdToArray"], ["777"])

    def test_portal_export_resets_wrong_dimension_and_reads_text_staff_numbers(self) -> None:
        people = parse_personnel_export(portal_export_bytes())
        self.assertEqual([(person.staff_number, person.name) for person in people], [
            ("000123", "测试甲"),
            ("000456", "测试乙"),
        ])

    def test_workbook_keeps_every_person_qualification_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "名册.xlsx"
            workbook = RosterWorkbook(target)
            workbook.append_qualification("RAMA", [
                PersonQualification("000123", "测试甲", "RAMA"),
                PersonQualification("000123", "测试甲", "RAMA"),
            ])
            workbook.append_qualification("EAMA", [PersonQualification("000123", "测试甲", "EAMA")])
            rows = workbook.read_rows()
            self.assertEqual(rows, [
                [1, "000123", "测试甲", "RAMA"],
                [2, "000123", "测试甲", "RAMA"],
                [3, "000123", "测试甲", "EAMA"],
            ])


if __name__ == "__main__":
    unittest.main()
