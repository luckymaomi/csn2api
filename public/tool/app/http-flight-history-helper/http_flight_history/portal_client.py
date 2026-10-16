from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import (
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
)
from ieb_protocol.flight_detail import FlightDetailProtocol

from .models import QueryRecord, TableResult
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


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
            "http-flight-history-cookie-keepalive",
        )
        self.ieb: IebSession | None = None
        self.protocol: FlightDetailProtocol | None = None
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
        protocol = FlightDetailProtocol(ieb)
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

    def _protocol(self) -> FlightDetailProtocol:
        if self.protocol is None:
            raise PortalSessionExpired("请先验证登录凭据")
        return self.protocol

    def check_session(self) -> None:
        self._protocol().check_session()

    def require_credentials(self) -> None:
        self._protocol().session.require_credentials()

    def query(self, record: QueryRecord) -> TableResult:
        _response, headers, rows = self._protocol().request_history(record.employee_id, record.name)
        return TableResult(headers=headers, rows=rows)

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
