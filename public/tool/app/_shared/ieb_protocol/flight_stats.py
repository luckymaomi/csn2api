from __future__ import annotations

from .base import IebSession
from .flight_stats_contract import build_query_params, parse_result_table, validate_query_page


QUERY_PAGE_PATH = "/newieb/flytime/showFlytimeManyQuery"
QUERY_PATH = "/newieb/flytime/showFlytimeManyQueryList"


class FlightStatsProtocol:
    """飞行经历查询页验证和单人完整结果请求。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session

    def validate_session(self) -> tuple[object, dict[str, str]]:
        response = self.session.request(
            "GET", QUERY_PAGE_PATH,
            data=None,
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        validate_query_page(str(response.text or ""), response.status_code)
        _identity_response, identity = self.session.fetch_identity()
        return response, identity

    def check_session(self) -> None:
        response = self.session.request(
            "GET", QUERY_PAGE_PATH,
            data=None,
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        validate_query_page(str(response.text or ""), response.status_code)

    def request_query(
        self,
        staff_number: str,
        start_date: str,
        end_date: str,
        expected_name: str = "",
    ) -> tuple[object, list[str], dict[str, str]]:
        response = self.session.request(
            "GET", QUERY_PATH,
            params=build_query_params(staff_number, start_date, end_date),
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        headers, row = parse_result_table(
            str(response.text or ""), staff_number, expected_name,
        )
        return response, headers, row
