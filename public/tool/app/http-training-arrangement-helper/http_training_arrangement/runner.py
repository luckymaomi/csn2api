from __future__ import annotations

import threading
from collections.abc import Callable

from datetime import date

from .area_defaults import ResolvedAreaCategory, area_summary, merge_area_windows
from .models import AreaQueryResult, AreaWindow, Event, QueryInput, QueryResult
from .portal_client import PortalSessionExpired


class QueryRunner:
    def __init__(
        self,
        portal: object,
        stop_event: threading.Event,
        emit: Callable[[Event], None],
    ) -> None:
        self.portal = portal
        self.stop_event = stop_event
        self.emit = emit

    def run(self, query_input: QueryInput) -> QueryResult:
        session_expired = False
        try:
            def on_event(event: dict[str, object]) -> None:
                if event.get("period"):
                    self.emit({"type": "period_started", **event})
                elif event.get("page"):
                    self.emit({"type": "page_completed", **event})

            windows = self.portal.query(query_input, on_event)  # type: ignore[attr-defined]
        except PortalSessionExpired as error:
            session_expired = True
            self.emit({"type": "error", "message": str(error)})
            return QueryResult([], interrupted=False, session_expired=True)
        if self.stop_event.is_set():
            self.emit({"type": "log", "level": "warning", "message": "已请求停止，当前请求完成后结束"})
            return QueryResult(windows, interrupted=True)
        return QueryResult(windows, session_expired=session_expired)


class AreaDefaultRunner:
    """按固定业务分类串行查询全部科目，并将结果投影为分类明细。"""

    def __init__(
        self,
        portal: object,
        stop_event: threading.Event,
        emit: Callable[[Event], None],
    ) -> None:
        self.portal = portal
        self.stop_event = stop_event
        self.emit = emit

    def run(self, categories: list[ResolvedAreaCategory], end_date: date) -> AreaQueryResult:
        windows: list[AreaWindow] = []
        for category_index, category in enumerate(categories):
            for subject in category.subjects:
                if self.stop_event.is_set():
                    merged = merge_area_windows(windows)
                    return AreaQueryResult(merged, area_summary(categories[:category_index + 1], merged), interrupted=True)
                self.emit({"type": "area_subject_started", "category": category.name, "subject": subject.label})

                received_windows = 0

                def publish(window: object, *, current=category.name) -> None:
                    nonlocal received_windows
                    received_windows += 1
                    windows.append(
                        AreaWindow(
                            current,
                            str(getattr(window, "key")),
                            str(getattr(window, "label")),
                            getattr(window, "start"),
                            getattr(window, "end"),
                            ["区域类型", *list(getattr(window, "headers"))],
                            [{"区域类型": current, **row} for row in getattr(window, "rows")],
                            int(getattr(window, "pages")),
                            getattr(window, "total"),
                        )
                    )
                    merged = merge_area_windows(windows)
                    self.emit({
                        "type": "area_results_updated",
                        "windows": merged,
                        "summary": area_summary(categories[:category_index + 1], merged),
                    })

                def on_event(event: dict[str, object], *, current=category.name, label=subject.label) -> None:
                    if event.get("period"):
                        self.emit({"type": "period_started", "category": current, "subject": label, **event})
                    elif event.get("page"):
                        self.emit({"type": "page_completed", "category": current, "subject": label, **event})
                    elif event.get("window") is not None:
                        publish(event["window"])

                try:
                    query_result = self.portal.query(  # type: ignore[attr-defined]
                        QueryInput(subject.value, "all", end_date), on_event
                    )
                except PortalSessionExpired:
                    merged = merge_area_windows(windows)
                    return AreaQueryResult(merged, area_summary(categories[:category_index + 1], merged), session_expired=True)
                if received_windows == 0:
                    for window in query_result:
                        publish(window)
                self.emit({"type": "area_subject_completed", "category": category.name, "subject": subject.label})
        merged = merge_area_windows(windows)
        return AreaQueryResult(merged, area_summary(categories, merged))
