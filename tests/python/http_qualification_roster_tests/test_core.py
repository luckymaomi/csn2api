from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from .common import APP_ROOT, PORTAL_PERSON_HEADERS, person_row, portal_export_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, PORTAL_PERSON_HEADERS, person_row, portal_export_bytes  # type: ignore[no-redef]  # noqa: F401

from http_qualification_roster.exporter import RosterWorkbook
from ieb_protocol.roster_models import CAP_TECHNICAL_LEVELS, QueryFilters
from ieb_protocol.qualification_roster import QualificationRosterProtocol
from http_qualification_roster.portal_client import (
    build_filter_params,
    parse_ooxml_rows,
    parse_operating_qualifications,
    project_personnel_rows,
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
    def test_keepalive_checks_identity_without_loading_filter_metadata(self) -> None:
        class IdentitySession:
            def __init__(self) -> None:
                self.identity_calls = 0

            def fetch_identity(self) -> tuple[object, dict[str, str]]:
                self.identity_calls += 1
                return object(), {"staffNumber": "900001", "name": "测试用户"}

            def request(self, *_args: object, **_kwargs: object) -> object:
                raise AssertionError("保活不应请求筛选或运行资格接口")

        session = IdentitySession()
        QualificationRosterProtocol(session).check_session()  # type: ignore[arg-type]
        self.assertEqual(session.identity_calls, 1)

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

    def test_cap_alias_expands_to_all_captain_and_instructor_levels(self) -> None:
        filters = QueryFilters.from_payload({"qualTypeArray": ["CAP"]})
        self.assertEqual(filters.technical_levels, list(CAP_TECHNICAL_LEVELS))
        params = build_filter_params(filters, "")
        self.assertEqual(
            [value for name, value in params if name == "qualTypeArray"],
            list(CAP_TECHNICAL_LEVELS),
        )
        self.assertEqual([value for name, value in params if name == "operQualArray"], [""])

    def test_portal_export_projects_page_columns_and_drops_selection_column(self) -> None:
        export_headers, export_rows = parse_ooxml_rows(portal_export_bytes())
        columns, people = project_personnel_rows(["#", *PORTAL_PERSON_HEADERS], export_headers, export_rows)
        self.assertEqual(columns, PORTAL_PERSON_HEADERS)
        self.assertEqual([(person["员工号"], person["姓名"]) for person in people], [
            ("000123", "测试甲"), ("000456", "测试乙"),
        ])
        self.assertNotIn("#", people[0])
        self.assertNotIn("运行资格", people[0])

    def test_portal_export_rejects_page_column_missing_from_native_export(self) -> None:
        with self.assertRaisesRegex(Exception, "门户普通导出缺少页面字段"):
            project_personnel_rows(["#", "员工号", "姓名", "不存在字段"], ["员工号", "姓名"], [{"员工号": "000123", "姓名": "测试甲"}])

    def test_workbook_keeps_every_person_qualification_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "名册.xlsx"
            workbook = RosterWorkbook(target)
            workbook.append_qualification("RAMA", PORTAL_PERSON_HEADERS, [person_row(), person_row()])
            workbook.append_qualification("EAMA", PORTAL_PERSON_HEADERS, [person_row()])
            self.assertEqual(workbook.read_headers(), ["序号", *PORTAL_PERSON_HEADERS, "资质类别"])
            rows = workbook.read_rows()
            self.assertEqual([row[0] for row in rows], [1, 2, 3])
            self.assertEqual([row[1] for row in rows], ["000123", "000123", "000123"])
            self.assertEqual([row[-1] for row in rows], ["RAMA", "RAMA", "EAMA"])


if __name__ == "__main__":
    unittest.main()
