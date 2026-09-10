from __future__ import annotations

from datetime import date, datetime
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
from ieb_protocol.training_arrangement import TrainingArrangementProtocol
from ieb_protocol.training_arrangement_models import TrainingOption, TrainingWindow

from .models import QueryInput
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


class PortalClient:
    """APP 会话适配器；训练安排请求和解析由共享 IEB core 执行。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 60,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.ieb = IebSession(session, base_url, timeout)
        self.protocol = TrainingArrangementProtocol(self.ieb)
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory, timeout, "http-training-arrangement-cookie-keepalive"
        )
        self.copyable_credentials = ""
        self.verified_at = ""
        self.options: list[TrainingOption] = []

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity

    @property
    def verified(self) -> bool:
        return bool(self.ieb.cookies)

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        cookies = self.ieb.load_credentials(source)
        try:
            _response, options = self.protocol.request_options()
            _identity_response, identity = self.ieb.fetch_identity()
        except Exception:
            self.ieb.clear_credentials()
            raise
        self.options = list(options)
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "identity": identity,
        }

    def load_options(self) -> list[TrainingOption]:
        self.require_credentials()
        _response, options = self.protocol.request_options()
        self.options = list(options)
        return list(self.options)

    def check_session(self) -> None:
        self.protocol.check_session()

    def require_credentials(self) -> None:
        self.ieb.require_credentials()

    def query(
        self,
        query_input: QueryInput,
        emit: Callable[[dict[str, object]], None] | None = None,
    ) -> list[TrainingWindow]:
        self.require_credentials()
        _response, windows = self.protocol.request_periods(
            query_input.category, query_input.end_date, query_input.date_range, emit=emit
        )
        return windows

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        self.options = []
        self.ieb.clear_credentials()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.keepalive.stop()
        self.ieb.close()


__all__ = ["PortalClient", "PortalError", "PortalSessionExpired"]
