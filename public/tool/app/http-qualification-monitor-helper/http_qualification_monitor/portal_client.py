from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import (
    BASE_URL,
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
)
from ieb_protocol.qualification_monitor import QualificationMonitorProtocol
from ieb_protocol.qualification_monitor_models import QualificationGroup

from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


class PortalClient:
    """APP 适配器：维护批量导出状态，生产调用由共享核心执行。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 60,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.ieb = IebSession(session, base_url, timeout)
        self.protocol = QualificationMonitorProtocol(self.ieb)
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-qualification-monitor-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def session(self) -> object:
        return self.ieb.session

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity

    @property
    def verified(self) -> bool:
        return bool(self.ieb.cookies)

    def load_credentials(self, source: str) -> tuple[dict[str, object], list[QualificationGroup]]:
        self.clear_credentials()
        cookies = self.ieb.load_credentials(source)
        try:
            groups, identity = self.protocol.load_metadata()
        except Exception:
            self.ieb.clear_credentials()
            raise
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "qualificationCount": sum(len(group.items) for group in groups),
            "identity": identity,
        }, groups

    def check_session(self) -> None:
        self.protocol.check_session()

    def require_credentials(self) -> None:
        self.ieb.require_credentials()

    def export_qualification(self, qualification_code: str) -> bytes:
        self.require_credentials()
        _response, content = self.protocol.request_export(qualification_code)
        return content

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        self.ieb.clear_credentials()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.keepalive.stop()
        self.ieb.close()


__all__ = [
    "PortalClient",
    "PortalError",
    "PortalSessionExpired",
]
