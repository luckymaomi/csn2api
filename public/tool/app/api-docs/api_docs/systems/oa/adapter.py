from __future__ import annotations

from typing import Callable

import requests

from oa_protocol import (
    OaProtocolClient,
    OaProtocolError,
    OaSessionExpired,
    credential_summary,
    format_credentials,
)

from ...catalog import ApiCatalog, EndpointRecord
from ..errors import ExecutionError, SessionExpiredError
from ..session_keepalive import SessionKeepAlive
from .workflows import execute_count, execute_read


class OaAdapter:
    """OA 会话入口；分页与已阅生产调用由共享 core 执行。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = lambda: 45,
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.protocol: OaProtocolClient | None = None
        self.cookies: dict[str, str] = {}
        self.keepalive = SessionKeepAlive(keepalive_interval_factory, timeout_seconds, "oa-cookie-keepalive")

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        protocol = OaProtocolClient(self.session_factory, timeout_seconds=self.timeout_seconds)
        try:
            cookies, _identity = protocol.load_credentials(source)
        except OaSessionExpired as error:
            protocol.close()
            raise SessionExpiredError(str(error)) from error
        except OaProtocolError as error:
            protocol.close()
            raise ExecutionError(str(error)) from error
        self.protocol, self.cookies = protocol, cookies
        self.keepalive.record_success()
        self.keepalive.start(self._check_session)
        return {**self.session_status(), "credentials": format_credentials(cookies)}

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.cookies = {}
        if self.protocol is not None:
            self.protocol.close()
        self.protocol = None

    def session_status(self) -> dict[str, object]:
        return {
            **credential_summary(self.cookies),
            "ready": bool(self.cookies),
            "identity": dict(self.protocol.identity) if self.protocol and self.protocol.identity else None,
            "keepAlive": self.keepalive.status(bool(self.cookies)),
        }

    def _core(self) -> OaProtocolClient:
        if self.protocol is None or not self.cookies:
            raise SessionExpiredError("请先载入有效 OA Cookie")
        return self.protocol

    def execute(
        self,
        record: EndpointRecord,
        supplied: dict[str, object],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        try:
            if record.full_id == "oa-read.count":
                return execute_count(record, self._core())
            if record.full_id == "oa-read.read":
                return execute_read(record, supplied, self._core(), progress_callback)
            raise ExecutionError("当前 OA 系统不支持该业务接口")
        except OaSessionExpired as error:
            self.clear_credentials()
            self.keepalive.mark_expired()
            raise SessionExpiredError(str(error)) from error
        except OaProtocolError as error:
            raise ExecutionError(str(error)) from error

    def _check_session(self) -> None:
        try:
            self._core().check_session()
        except OaSessionExpired as error:
            self.clear_credentials()
            raise SessionExpiredError(str(error)) from error

    def close(self) -> None:
        self.clear_credentials()
