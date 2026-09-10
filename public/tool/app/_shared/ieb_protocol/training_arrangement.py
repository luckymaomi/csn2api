from __future__ import annotations

import time
from datetime import date
from typing import Callable

from .base import IebContractError, IebSession
from .training_arrangement_contract import (
    ARRANGEMENT_PATH,
    TRAINING_PAGE_PATH,
    build_query_params,
    display_window,
    parse_training_options,
    parse_training_page,
    period_windows,
    row_fingerprint,
    window_result,
)
from .training_arrangement_models import TrainingOption, TrainingPage, TrainingWindow


class TrainingArrangementProtocol:
    """IEB 已结束训练安排查询、动态类别和严格串行分页。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session

    def request_options(self) -> tuple[object, list[TrainingOption]]:
        response = self.session.request(
            "GET", TRAINING_PAGE_PATH, params={"trainSectionName": "end"},
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        return response, parse_training_options(str(response.text or ""))

    def check_session(self) -> None:
        self.request_options()

    def request_page(self, category: str, start: date, end: date, page: int = 1) -> tuple[object, TrainingPage]:
        params = build_query_params(category, start, end, page)
        params["currentStr"] = str(int(time.time() * 1000))
        response = self.session.request(
            "POST", ARRANGEMENT_PATH, params={"trainSectionName": "end"}, data=params,
            headers={"Accept": "text/html, */*; q=0.01", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        return response, parse_training_page(str(response.text or ""), page)

    def request_window(
        self,
        category: str,
        start: date,
        end: date,
        max_pages: int = 100,
        emit: Callable[[dict[str, object]], None] | None = None,
    ) -> tuple[object, TrainingWindow]:
        if max_pages < 1:
            raise ValueError("最大页数必须大于 0")
        pages: list[TrainingPage] = []
        seen_pages: set[tuple[str, ...]] = set()
        last_response: object | None = None
        for page_number in range(1, max_pages + 1):
            response, page = self.request_page(category, start, end, page_number)
            last_response = response
            fingerprints = tuple(row_fingerprint(row) for row in page.rows)
            if fingerprints and fingerprints in seen_pages:
                break
            seen_pages.add(fingerprints)
            pages.append(page)
            if emit:
                emit({"page": page_number, "rows": len(page.rows)})
            if not page.rows:
                break
            total = page.total
            if total is not None and sum(len(item.rows) for item in pages) >= total:
                break
        else:
            raise IebContractError("训练安排分页超过 100 页，已停止以避免异常循环")
        if last_response is None:
            raise IebContractError("训练安排没有收到响应")
        return last_response, window_result("custom", "自定义", start, end, pages)

    def request_periods(
        self,
        category: str,
        end: date,
        period: str = "all",
        emit: Callable[[dict[str, object]], None] | None = None,
    ) -> tuple[object, list[TrainingWindow]]:
        last_response: object | None = None
        windows: list[TrainingWindow] = []
        for key, label, start, window_end in period_windows(end, period):
            if emit:
                emit({"period": key, "label": label, "start": start.isoformat(), "end": window_end.isoformat()})
            response, result = self.request_window(category, start, window_end, emit=emit)
            last_response = response
            windows.append(
                TrainingWindow(key, label, start, window_end, result.headers, result.rows, result.pages, result.total)
            )
            if emit:
                emit({"window": windows[-1]})
        if last_response is None:
            raise IebContractError("没有选择时间范围")
        return last_response, windows

    @staticmethod
    def display(windows: list[TrainingWindow]) -> list[dict[str, object]]:
        return [display_window(window) for window in windows]
