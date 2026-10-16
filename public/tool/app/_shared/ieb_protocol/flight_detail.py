from __future__ import annotations

import time

from .base import IebSession
from .flight_detail_contract import (
    DETAIL_PATH,
    QUERY_PAGE_PATH,
    TIMELINE_PATH,
    build_detail_params,
    parse_detail_table,
    parse_timeline,
    validate_detail_query_page,
    resolve_month_fleet,
)


class FlightDetailProtocol:
    """IEB 月度逐航班明细的共享请求与响应协议。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session

    def validate_session(self) -> tuple[object, dict[str, str]]:
        response = self.session.request(
            "GET", QUERY_PAGE_PATH, data=None,
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        validate_detail_query_page(str(response.text or ""), response.status_code)
        identity_response, identity = self.session.fetch_identity()
        return identity_response, identity

    def check_session(self) -> None:
        response = self.session.request(
            "GET", QUERY_PAGE_PATH, data=None,
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        validate_detail_query_page(str(response.text or ""), response.status_code)

    def request_timeline_response(self, staff_number: str) -> object:
        response = self.session.request(
            "POST", TIMELINE_PATH,
            data={"staffNum": staff_number, "currentStr": str(time.time_ns())},
            headers={"Origin": self.session.base_url, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        response.encoding = "utf-8"
        return response

    def request_timeline(self, staff_number: str, expected_name: str = "") -> list[dict[str, str]]:
        response = self.request_timeline_response(staff_number)
        return parse_timeline(str(response.text or ""), staff_number, expected_name)

    def request_history(self, staff_number: str, name: str) -> tuple[object, list[str], list[dict[str, str]]]:
        from .flight_history_contract import parse_history

        response = self.request_timeline_response(staff_number)
        headers, values = parse_history(str(response.text or ""), staff_number, name)
        return response, headers, values

    def request_month(
        self,
        staff_number: str,
        name: str,
        month: str,
        timeline: list[dict[str, str]],
    ) -> tuple[object, list[str], list[dict[str, str]]]:
        fleet = resolve_month_fleet(timeline, month)
        if not fleet:
            from .base import IebContractError
            raise IebContractError(f"{month} 未找到动态机型参数")
        response = self.session.request(
            "GET", DETAIL_PATH,
            params=build_detail_params(staff_number, name, month, fleet),
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        headers, rows = parse_detail_table(str(response.text or ""))
        return response, headers, rows
