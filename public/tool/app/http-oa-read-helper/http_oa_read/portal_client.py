from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from oa_protocol import (
    OaBusinessError,
    OaProtocolClient,
    OaProtocolError,
    OaSessionExpired,
    credential_summary,
    format_credentials,
)
from oa_protocol.models import ScanSnapshot, WaitingRecord

from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = OaProtocolError
PortalBusinessError = OaBusinessError
PortalSessionExpired = OaSessionExpired


class PortalClient:
    """APP 适配器：维护页面凭据状态，生产调用由 OA core 执行。"""

    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.protocol = OaProtocolClient(session_factory, timeout_seconds=timeout_seconds)
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout_seconds,
            "http-oa-read-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def identity(self) -> dict[str, str] | None:
        return self.protocol.identity

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        cookies, identity = self.protocol.load_credentials(source)
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {**credential_summary(cookies), "verifiedAt": self.verified_at, "identity": dict(identity)}

    def check_session(self) -> None:
        self.protocol.check_session()

    def scan_waiting(self) -> ScanSnapshot:
        return self.protocol.scan_waiting()

    def mark_read(self, record: WaitingRecord) -> None:
        self.protocol.mark_read(record)

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        self.protocol.clear_credentials()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.keepalive.stop()
        self.protocol.close()


__all__ = [
    "PortalBusinessError",
    "PortalClient",
    "PortalError",
    "PortalSessionExpired",
]
