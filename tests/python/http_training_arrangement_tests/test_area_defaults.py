from __future__ import annotations

import threading
import unittest
from datetime import date

from .common import SHARED_ROOT  # noqa: F401
from ieb_protocol.training_arrangement_models import TrainingOption, TrainingWindow
from http_training_arrangement.area_defaults import AREA_DEFAULTS, ResolvedAreaCategory, area_details, area_summary, merge_area_windows, outcome, resolve_area_defaults
from http_training_arrangement.models import AreaWindow
from http_training_arrangement.runner import AreaDefaultRunner


def options() -> list[TrainingOption]:
    return [TrainingOption(f"code-{index}", subject) for index, subject in enumerate(
        subject for category in AREA_DEFAULTS for subject in category.subjects
    )]


class AreaDefaultTests(unittest.TestCase):
    def test_resolves_all_user_categories_by_dynamic_labels(self) -> None:
        resolved = resolve_area_defaults(options())
        self.assertEqual([item.name for item in resolved], [item.name for item in AREA_DEFAULTS])
        self.assertEqual(len(resolved[7].subjects), 3)

    def test_missing_or_duplicate_subject_is_rejected(self) -> None:
        values = options()
        values.pop(0)
        with self.assertRaisesRegex(ValueError, "缺少"):
            resolve_area_defaults(values)
        values = options()
        values.append(TrainingOption("duplicate", values[0].label))
        with self.assertRaisesRegex(ValueError, "重复"):
            resolve_area_defaults(values)

    def test_outcome_and_summary_use_complete_and_terminated_only(self) -> None:
        self.assertEqual(outcome({"训练状态": "终止"}), "failed")
        self.assertEqual(outcome({"训练状态": "完成"}), "passed")
        with self.assertRaisesRegex(ValueError, "训练状态不受支持"):
            outcome({"训练状态": "进行中"})
        window = AreaWindow(
            "区域航线", "week", "周", date(2026, 9, 3), date(2026, 9, 10),
            ["区域类型", "训练状态"],
            [{"区域类型": "区域航线", "训练状态": "完成"}, {"区域类型": "区域航线", "训练状态": "终止"}],
            1,
            2,
        )
        summary = area_summary(resolve_area_defaults(options()), [window])
        self.assertEqual(summary[0]["week"], {"count": 2, "passed": 1, "rate": 50.0})
        self.assertIsNone(summary[0]["month"]["rate"])

    def test_runner_publishes_page_progress_and_partial_results_after_each_subject(self) -> None:
        categories = resolve_area_defaults(options())[:2]
        events: list[dict[str, object]] = []

        class Portal:
            def query(self, query_input, emit=None):
                values = []
                for key, label in (("week", "周"), ("month", "月"), ("year", "年")):
                    window = TrainingWindow(
                        key, label, date(2026, 1, 1), date(2026, 9, 10),
                        ["训练状态"], [{"训练状态": "完成"}], 1, 1,
                    )
                    if emit:
                        emit({"period": key, "label": label, "start": "2026-01-01", "end": "2026-09-10"})
                        emit({"page": 1, "rows": 1})
                        emit({"window": window})
                    values.append(window)
                return values

        result = AreaDefaultRunner(Portal(), threading.Event(), events.append).run(categories, date(2026, 9, 10))
        event_types = [event.get("type") for event in events]
        self.assertIn("period_started", event_types)
        self.assertIn("page_completed", event_types)
        updates = [event for event in events if event.get("type") == "area_results_updated"]
        self.assertEqual(len(updates), 6)
        self.assertEqual(len(updates[0]["windows"]), 1)
        self.assertEqual(len(updates[0]["summary"]), 1)
        self.assertEqual(len(result.windows), 6)
        self.assertEqual(len(merge_area_windows(result.windows)), 6)

    def test_deduplicates_same_arrangement_across_subjects_and_periods(self) -> None:
        row = {"训练科目": "STC机长转机型一级航检", "员工号/姓名": "900001 (测试)", "训练状态": "完成"}
        windows = [
            AreaWindow("航线一检", "week", "周", date(2026, 9, 3), date(2026, 9, 10), ["区域类型", *row], [{"区域类型": "航线一检", **row}], 1, 1),
            AreaWindow("航线一检", "week", "周", date(2026, 9, 3), date(2026, 9, 10), ["区域类型", *row], [{"区域类型": "航线一检", **row}], 1, 1),
            AreaWindow("航线一检", "month", "月", date(2026, 9, 1), date(2026, 9, 10), ["区域类型", *row], [{"区域类型": "航线一检", **row}], 1, 1),
            AreaWindow("航线一检", "year", "年", date(2026, 1, 1), date(2026, 9, 10), ["区域类型", *row], [{"区域类型": "航线一检", **row}], 1, 1),
        ]
        merged = merge_area_windows(windows)
        self.assertEqual(len(merged), 3)
        self.assertEqual(len(merged[0].rows), 1)
        headers, details = area_details(merged)
        self.assertIn("所属周期", headers)
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["所属周期"], "周、月、年")

    def test_three_subject_category_counts_zero_plus_one_plus_zero_as_one(self) -> None:
        category = ResolvedAreaCategory("航线一检", (
            TrainingOption("stc", "STC机长转机型一级航检"),
            TrainingOption("heavy", "非STC机长转机型一级航检（大转重）"),
            TrainingOption("other", "非STC机长转机型一级航检（非大转重）"),
        ))

        class Portal:
            def query(self, query_input, emit=None):
                rows = [{
                    "训练科目": "非STC机长转机型一级航检（大转重）",
                    "员工号/姓名": "900001 (测试)",
                    "训练状态": "完成",
                }] if query_input.category == "heavy" else []
                window = TrainingWindow(
                    "week", "周", date(2026, 9, 3), date(2026, 9, 10),
                    ["训练科目", "员工号/姓名", "训练状态"], rows, 1, len(rows),
                )
                if emit:
                    emit({"period": "week", "label": "周", "start": "2026-09-03", "end": "2026-09-10"})
                    emit({"page": 1, "rows": len(rows)})
                    emit({"window": window})
                return [window]

        result = AreaDefaultRunner(Portal(), threading.Event(), lambda _event: None).run([category], date(2026, 9, 10))
        self.assertEqual(result.summary[0]["week"]["count"], 1)
        self.assertEqual(len(area_details(result.windows)[1]), 1)


if __name__ == "__main__":
    unittest.main()
