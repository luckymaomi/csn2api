from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import (
    IebContractError,
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
)
from ieb_protocol.base import parse_current_identity as _parse_current_identity
from ieb_protocol.flight_stats import FlightStatsProtocol
from ieb_protocol.flight_stats_contract import (
    build_query_params as _build_query_params,
    parse_result_table as _parse_result_table,
)

from .models import QueryRecord, TableResult
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


def parse_current_identity(html: str, status_code: int) -> dict[str, str]:
    try:
        return _parse_current_identity(html, status_code)
    except IebContractError as error:
        raise ValueError(str(error)) from error


def parse_result_table(html: str, expected_employee_id: str, expected_name: str = "") -> TableResult:
    try:
        headers, values = _parse_result_table(html, expected_employee_id, expected_name)
    except IebContractError as error:
        raise ValueError(str(error)) from error
    return TableResult(headers=headers, values=values)


def build_query_params(record: QueryRecord) -> dict[str, str]:
    return _build_query_params(
        record.employee_id,
        record.start_date.isoformat(),
        record.end_date.isoformat(),
    )


class PortalClient:
    """APP 适配器：补充批量会话状态，单人请求由共享核心执行。"""

    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout_seconds,
            "http-flight-stats-cookie-keepalive",
        )
        self.ieb: IebSession | None = None
        self.protocol: FlightStatsProtocol | None = None
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def cookies(self) -> dict[str, str]:
        return self.ieb.cookies if self.ieb is not None else {}

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity if self.ieb is not None else None

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        ieb = IebSession(self.session_factory(), timeout=self.timeout_seconds)
        cookies = ieb.load_credentials(source)
        protocol = FlightStatsProtocol(ieb)
        try:
            _response, identity = protocol.validate_session()
        except Exception:
            ieb.close()
            raise
        self.ieb = ieb
        self.protocol = protocol
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "identity": identity,
        }

    def _protocol(self) -> FlightStatsProtocol:
        if self.protocol is None:
            raise PortalSessionExpired("请先验证登录凭据")
        return self.protocol

    def check_session(self) -> None:
        self._protocol().check_session()

    def require_credentials(self) -> None:
        self._protocol().session.require_credentials()

    def query(self, record: QueryRecord) -> TableResult:
        _response, headers, values = self._protocol().request_query(
            record.employee_id,
            record.start_date.isoformat(),
            record.end_date.isoformat(),
            record.name,
        )
        return TableResult(headers=headers, values=values)

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        if self.ieb is not None:
            self.ieb.close()
        self.ieb = None
        self.protocol = None

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.clear_credentials()
