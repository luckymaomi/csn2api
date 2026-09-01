from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import IebContractError, IebSession, IebSessionExpired, credential_summary, format_credentials
from ieb_protocol.flight_detail import FlightDetailProtocol

from .models import MonthOutcome, QueryRecord
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = RuntimeError
PortalSessionExpired = IebSessionExpired


class PortalClient:
    def __init__(self, session_factory: Callable[[], requests.Session] = requests.Session, timeout_seconds: int = 30, keepalive_interval_factory: Callable[[], int] = random_keepalive_interval) -> None:
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.keepalive = SessionKeepAlive(keepalive_interval_factory, timeout_seconds, "http-flight-detail-cookie-keepalive")
        self.ieb: IebSession | None = None
        self.protocol: FlightDetailProtocol | None = None
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity if self.ieb is not None else None

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        ieb = IebSession(self.session_factory(), timeout=self.timeout_seconds)
        cookies = ieb.load_credentials(source)
        protocol = FlightDetailProtocol(ieb)
        try:
            _response, identity = protocol.validate_session()
        except Exception:
            ieb.close()
            raise
        self.ieb, self.protocol = ieb, protocol
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {**credential_summary(cookies), "verifiedAt": self.verified_at, "identity": identity}

    def require_credentials(self) -> None:
        if self.protocol is None:
            raise PortalSessionExpired("请先验证登录凭据")

    def check_session(self) -> None:
        self.require_credentials()
        self.protocol.check_session()  # type: ignore[union-attr]

    def query_month(self, record: QueryRecord, month: str, timeline: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
        self.require_credentials()
        _response, headers, rows = self.protocol.request_month(record.employee_id, record.name, month, timeline)  # type: ignore[union-attr]
        return headers, rows

    def load_timeline(self, record: QueryRecord) -> list[dict[str, str]]:
        self.require_credentials()
        return self.protocol.request_timeline(record.employee_id, record.name)  # type: ignore[union-attr]

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        if self.ieb is not None:
            self.ieb.close()
        self.ieb = self.protocol = None

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.clear_credentials()

