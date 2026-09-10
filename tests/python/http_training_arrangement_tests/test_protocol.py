from __future__ import annotations

import re
import unittest
from datetime import date

from .common import SHARED_ROOT  # noqa: F401
from ieb_protocol.base import IebContractError
from ieb_protocol.training_arrangement_contract import (
    DISPLAY_HEADERS,
    build_query_params,
    parse_training_options,
    parse_training_page,
    period_windows,
)
from ieb_protocol.training_arrangement import TrainingArrangementProtocol
from ieb_protocol.training_arrangement_models import TrainingWindow


HTML = """
<div id="showArrangementListJspId">
  <div class="hDiv"><table><tr>
    <th><div>#</div></th><th><div></div></th><th><div>训练大纲</div></th><th><div>训练科目</div></th>
    <th><div>员工号/姓名</div></th><th><div>申请描述</div></th><th><div>检查项</div></th><th><div>注册基地</div></th>
    <th><div>运行基地</div></th><th><div>所属分部</div></th><th><div>审批过程</div></th><th><div>录入结果</div></th>
    <th><div>训练状态</div></th><th><div>检查员</div></th><th><div>检查日期</div></th><th><div>航班信息</div></th>
  </tr></table></div>
  <div class="bDiv"><table><tr>
    <td>1</td><td></td><td>777</td><td>机长等级训练C转D</td><td>215060 (测试甲)</td><td title="完整申请描述">申请...</td>
    <td></td><td>货航</td><td>广州</td><td>一分部</td><td>查看详细</td><td>查看结果</td><td>完成</td>
    <td>检查员甲(181524)</td><td>2026-03-17</td><td title="2579,2026-03-14 04:30:00,CKG,AMS;">2579,CKG,AMS;</td>
  </tr></table></div>
</div>
<div class="footer"><a>共 1 条记录</a><input id="userPage" value="1"></div>
"""


class ProtocolTests(unittest.TestCase):
    def test_calculates_three_windows_using_inclusive_portal_dates(self) -> None:
        self.assertEqual(
            [(key, start.isoformat(), end.isoformat()) for key, _label, start, end in period_windows(date(2026, 9, 10))],
            [
                ("week", "2026-09-03", "2026-09-10"),
                ("month", "2026-09-01", "2026-09-10"),
                ("year", "2026-01-01", "2026-09-10"),
            ],
        )

    def test_builds_query_contract(self) -> None:
        params = build_query_params("jzdjxlCD", date(2026, 1, 1), date(2026, 9, 10), 2)
        self.assertEqual(params["trainItemArray"], "jzdjxlCD")
        self.assertEqual(params["checkStartDt"], "2026-01-01")
        self.assertEqual(params["checkEndDt"], "2026-09-10")
        self.assertEqual(params["page"], "2")

    def test_parses_flexgrid_separate_header_and_data_tables(self) -> None:
        page = parse_training_page(HTML)
        self.assertEqual(page.headers, DISPLAY_HEADERS)
        self.assertEqual(page.total, 1)
        self.assertEqual(len(page.rows), 1)
        self.assertEqual(page.rows[0]["训练科目"], "机长等级训练C转D")
        self.assertEqual(page.rows[0]["员工号/姓名"], "215060 (测试甲)")
        self.assertEqual(page.rows[0]["申请描述"], "完整申请描述")

    def test_rejects_missing_required_header(self) -> None:
        broken = HTML.replace("<th><div>航班信息</div></th>", "")
        with self.assertRaisesRegex(IebContractError, "表头异常|列数"):
            parse_training_page(broken)

    def test_ignores_portal_empty_placeholder_row_after_business_projection(self) -> None:
        placeholder = [""] * len(DISPLAY_HEADERS)
        placeholder[DISPLAY_HEADERS.index("训练状态")] = "完成"
        empty_cells = "<td>1</td><td></td>" + "".join(f"<td>{value}</td>" for value in placeholder)
        empty = re.sub(
            r"<div class=\"bDiv\"><table><tr>.*?</tr></table></div>",
            f'<div class="bDiv"><table><tr>{empty_cells}</tr></table></div>',
            HTML,
            flags=re.DOTALL,
        ).replace("共 1 条记录", "共 0 条记录")
        page = parse_training_page(empty)
        self.assertEqual(page.rows, [])
        self.assertEqual(page.total, 0)

    def test_ignores_portal_no_training_personnel_colspan_row(self) -> None:
        no_personnel = re.sub(
            r'<div class="bDiv"><table><tr>.*?</tr></table></div>',
            '<div class="bDiv"><table><tr><td colspan="16">没有训练班人员信息!</td></tr></table></div>',
            HTML,
            flags=re.DOTALL,
        ).replace("共 1 条记录", "共 0 条记录")
        page = parse_training_page(no_personnel)
        self.assertEqual(page.rows, [])
        self.assertEqual(page.total, 0)

    def test_only_counts_rows_with_employee_number_and_name(self) -> None:
        without_employee = HTML.replace("<td>215060 (测试甲)</td>", "<td></td>")
        self.assertEqual(parse_training_page(without_employee).rows, [])
        employee_only = HTML.replace("<td>215060 (测试甲)</td>", "<td>215060</td>")
        self.assertEqual(parse_training_page(employee_only).rows, [])
        name_only = HTML.replace("<td>215060 (测试甲)</td>", "<td>测试甲</td>")
        self.assertEqual(parse_training_page(name_only).rows, [])
        compact_identity = HTML.replace("<td>215060 (测试甲)</td>", "<td>900002(测试乙)</td>")
        self.assertEqual(len(parse_training_page(compact_identity).rows), 1)
        without_subject = HTML.replace("<td>机长等级训练C转D</td>", "<td></td>")
        self.assertEqual(len(parse_training_page(without_subject).rows), 1)

    def test_reads_dynamic_training_options(self) -> None:
        html = '<select id="trainItemArraySelId"><option value="">请选择</option><option value="jzdjxlCD">机长等级训练C转D</option></select>'
        options = parse_training_options(html)
        self.assertEqual([(item.value, item.label) for item in options], [("jzdjxlCD", "机长等级训练C转D")])

    def test_period_query_emits_each_completed_window_for_live_results(self) -> None:
        class Protocol(TrainingArrangementProtocol):
            def __init__(self) -> None:
                pass

            def request_window(self, category, start, end, max_pages=100, emit=None):
                if emit:
                    emit({"page": 1, "rows": 1})
                return object(), TrainingWindow(
                    "custom", "自定义", start, end, ["训练状态"], [{"训练状态": "完成"}], 1, 1,
                )

        events: list[dict[str, object]] = []
        _response, windows = Protocol().request_periods("code", date(2026, 9, 10), emit=events.append)
        completed = [event["window"] for event in events if event.get("window") is not None]
        self.assertEqual(len(windows), 3)
        self.assertEqual([window.key for window in completed], ["week", "month", "year"])


if __name__ == "__main__":
    unittest.main()
