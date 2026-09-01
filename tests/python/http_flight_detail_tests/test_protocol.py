from __future__ import annotations

import unittest

from .common import SHARED_ROOT  # noqa: F401
from ieb_protocol.base import IebContractError
from ieb_protocol.flight_detail_contract import (
    DETAIL_HEADERS,
    build_detail_params,
    parse_detail_table,
    parse_timeline,
    resolve_month_fleet,
)


TIMELINE_HTML = """
<div>
  <button onclick="showflyTimeDetail('1','900001','示例甲','2026','','32A')">2026</button>
  <button onclick="showflyTimeDetail('2','900001','示例甲','2026-08','','32A')">8月</button>
</div>
"""

DETAIL_HTML = """
<table><thead><tr>
  <th>序号</th><th>航班号</th><th>机型</th><th>日期</th><th>左座</th>
  <th>右座</th><th>操纵</th><th>观察</th><th>离场</th><th>到达</th>
  <th>飞行时间</th><th>夜航</th><th>飞行阶段</th><th>人工飞行时间</th><th>人工飞行方式</th>
</tr></thead><tbody>
  <tr><td rowspan="3">1</td><td title="CZ3001">CZ3001</td><td>32A</td><td>2026-08-01</td><td>1</td><td></td><td>1</td><td></td><td>CAN</td><td>PEK</td><td>03:10</td><td>01:00</td><td>巡航</td><td>00:12</td></tr>
  <tr><td>自动驾驶</td></tr><tr><td></td></tr>
  <tr><td rowspan="2">2</td><td>CZ3002</td><td>32A</td><td>2026-08-02</td><td></td><td>1</td><td></td><td>1</td><td>PEK</td><td>CAN</td><td>03:20</td><td></td><td>巡航</td><td></td></tr>
  <tr><td>人工操纵</td></tr>
</tbody></table>
"""


class FlightDetailContractTests(unittest.TestCase):
    def test_parses_real_timeline_shape_and_resolves_month_then_year_fleet(self) -> None:
        entries = parse_timeline(TIMELINE_HTML, "900001", "示例甲")

        self.assertEqual(len(entries), 2)
        self.assertEqual(resolve_month_fleet(entries, "2026-08"), "32A")
        self.assertEqual(resolve_month_fleet(entries, "2026-07"), "32A")

    def test_rejects_timeline_for_another_person(self) -> None:
        with self.assertRaisesRegex(IebContractError, "姓名"):
            parse_timeline(TIMELINE_HTML, "900001", "示例乙")

    def test_builds_confirmed_month_request_parameters(self) -> None:
        params = build_detail_params("900001", "示例甲", "2026-8", "32A")

        self.assertEqual(params, {
            "startStr": "2026-08",
            "endStr": "",
            "dateType": "2",
            "staffNum": "900001",
            "staffName": "示例甲",
            "fleetCdArray": "32A",
        })

    def test_parses_dynamic_row_groups_and_additional_flight_mode(self) -> None:
        headers, rows = parse_detail_table(DETAIL_HTML)

        self.assertEqual(headers, DETAIL_HEADERS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["航班号"], "CZ3001")
        self.assertEqual(rows[0]["人工飞行方式"], "自动驾驶")
        self.assertEqual(rows[1]["人工飞行方式"], "人工操纵")

    def test_accepts_header_only_as_empty_month_and_rejects_wrong_width(self) -> None:
        header_only = DETAIL_HTML.replace(DETAIL_HTML.split("<tbody>", 1)[1].split("</tbody>", 1)[0], "")
        _headers, rows = parse_detail_table(header_only)
        self.assertEqual(rows, [])

        broken = DETAIL_HTML.replace("<td>00:12</td></tr>", "</tr>", 1)
        with self.assertRaisesRegex(IebContractError, "列数"):
            parse_detail_table(broken)


if __name__ == "__main__":
    unittest.main()

