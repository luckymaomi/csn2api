from __future__ import annotations

import time
from typing import Callable

import requests

from caac_protocol import (
    BASE_URL,
    CaacContractError,
    CaacProtocolClient,
    CaacProtocolError,
    CaacSessionExpired,
    build_list_form,
    credential_summary,
    format_credentials,
    parse_pilot_page,
)

from .models import PilotRecord, PilotOutcome
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = CaacProtocolError
PortalSessionExpired = CaacSessionExpired
PortalContractError = CaacContractError


class PortalClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.protocol = CaacProtocolClient(session, base_url, timeout)
        self.session = self.protocol.session
        self.base_url = self.protocol.base_url
        self.timeout = timeout
        self.request_lock = self.protocol.request_lock
        self.keepalive = SessionKeepAlive(keepalive_interval_factory, timeout, "caac-pilot-cookie-keepalive")
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def cookies(self) -> dict[str, str]:
        return self.protocol.cookies

    @staticmethod
    def _list_form(page: int, rows: int = 10, pilotname: str = "", archive_no: str = "") -> dict[str, str]:
        return build_list_form(page, rows, {"pilotname": pilotname, "archiveNo": archive_no})

    _parse_page = staticmethod(parse_pilot_page)

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies, total = self.protocol.load_credentials(source)
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return {**credential_summary(cookies), "verifiedAt": self.verified_at, "total": total}

    def check_session(self) -> None:
        self.protocol.check_session()

    def require_credentials(self) -> None:
        if not self.cookies:
            raise PortalSessionExpired("请先验证 CAAC 登录凭据")

    def fetch_page(
        self,
        page: int,
        page_size: int = 10,
        *,
        pilotname: str = "",
        archive_no: str = "",
    ) -> tuple[list[dict[str, object]], int]:
        return self.protocol.fetch_page(
            page,
            page_size,
            filters={"pilotname": pilotname, "archiveNo": archive_no},
        )

    def fetch_all_pilots(self, page_size: int = 10) -> tuple[list[PilotRecord], int]:
        rows, total = self.protocol.fetch_all_rows(page_size)
        return [PilotRecord(index, row) for index, row in enumerate(rows)], total

    def resolve_pilot(self, requested: PilotRecord, page_size: int = 10) -> PilotRecord:
        listing, _scanned = self.protocol.resolve_by_name(
            requested.input_name,
            requested.input_archive_no,
            page_size,
            lambda page, size: self.fetch_page(
                page,
                size,
                pilotname=requested.input_name,
                archive_no=requested.input_archive_no,
            ),
        )
        return PilotRecord(
            requested.index,
            listing,
            requested.input_name,
            requested.input_archive_no,
            requested.source,
            "",
            requested.input_row,
        )

    def fetch_detail(self, pilot_id: str) -> dict[str, object]:
        return self.protocol.fetch_detail(pilot_id)

    def query_one(self, record: PilotRecord) -> PilotOutcome:
        resolved = record if record.pilot_id else self.resolve_pilot(record)
        return PilotOutcome(resolved, "成功", detail=self.fetch_detail(resolved.pilot_id))

    def invalidate_credentials(self) -> None:
        self.clear_credentials()

    def clear_credentials(self) -> None:
        self.protocol.clear_credentials()
        self.copyable_credentials = ""
        self.verified_at = ""

    def close(self) -> None:
        self.keepalive.stop()
        self.protocol.close()


__all__ = [
    "PortalClient",
    "PortalContractError",
    "PortalError",
    "PortalSessionExpired",
]
