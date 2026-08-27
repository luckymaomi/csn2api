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
from ieb_protocol.qualification_roster import QualificationRosterProtocol
from ieb_protocol.roster_contract import (
    build_filter_params,
    parse_filter_fields,
    parse_ooxml_rows,
    parse_operating_qualifications,
    personnel_columns,
    project_personnel_rows,
    parse_query_count,
    parse_query_result,
    validate_ooxml,
)
from ieb_protocol.roster_models import FilterField, OperatingQualification, QueryFilters

from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


class PortalClient:
    """APP 适配器：补充保活与状态，生产请求由共享核心执行。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        timeout: int = 60,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.ieb = IebSession(session, BASE_URL, timeout)
        self.protocol = QualificationRosterProtocol(self.ieb)
        self.session = self.ieb.session
        self.request_lock = self.ieb.request_lock
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-qualification-roster-cookie-keepalive",
        )
        self.verified = False
        self.copyable_credentials = ""
        self.verified_at = ""
        self.filter_fields: list[FilterField] = []
        self.qualifications: list[OperatingQualification] = []

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        cookies = self.ieb.load_credentials(source)
        try:
            _response, identity = self.protocol.validate_session()
        except Exception:
            self.ieb.clear_credentials()
            raise
        self.verified = True
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            **credential_summary(cookies),
            "identity": identity,
            "verifiedAt": self.verified_at,
        }

    def load_metadata(self) -> tuple[list[FilterField], list[OperatingQualification]]:
        self.require_credentials()
        fields, qualifications = self.protocol.load_metadata()
        self.filter_fields = fields
        self.qualifications = qualifications
        return fields, qualifications

    def keepalive_check(self) -> None:
        self.require_credentials()
        self.protocol.check_session()

    def check_session(self) -> None:
        self.keepalive_check()

    def require_credentials(self) -> None:
        if not self.verified:
            raise PortalSessionExpired("请先验证飞行门户 Cookie")
        self.ieb.require_credentials()

    def query_roster(self, filters: QueryFilters, qualification_code: str) -> tuple[int, list[str]]:
        self.require_credentials()
        _response, total, headers, _rows = self.protocol.request_query(filters, qualification_code)
        return total, personnel_columns(headers)

    def export_people(
        self,
        filters: QueryFilters,
        qualification_code: str,
        columns: list[str],
    ) -> list[dict[str, str]]:
        self.require_credentials()
        _response, content = self.protocol.request_export(filters, qualification_code)
        export_headers, export_rows = parse_ooxml_rows(content)
        _columns, people = project_personnel_rows(columns, export_headers, export_rows)
        return people

    def invalidate_credentials(self) -> None:
        self.verified = False
        self.copyable_credentials = ""
        self.verified_at = ""
        self.filter_fields = []
        self.qualifications = []
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
    "build_filter_params",
    "parse_filter_fields",
    "parse_ooxml_rows",
    "parse_operating_qualifications",
    "personnel_columns",
    "project_personnel_rows",
    "parse_query_count",
    "parse_query_result",
    "validate_ooxml",
]
