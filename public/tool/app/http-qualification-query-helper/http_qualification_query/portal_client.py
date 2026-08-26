from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import (
    BASE_URL,
    IebContractError,
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
)
from ieb_protocol.base import parse_current_identity as _parse_current_identity
from ieb_protocol.personnel import PersonnelProtocol
from ieb_protocol.personnel_contract import (
    BASIC_INFO_FIELDS,
    OPERATION_HEADERS,
    SECTION_FIELDS,
    TECHNICAL_HEADERS,
    TRAINING_EXPERIENCE_HEADERS,
    TRAINING_RECORD_HEADERS,
    build_employee_query_params,
    parse_basic_payload,
    parse_detail_table,
    parse_employee_identity,
    parse_training_record_pages,
)

from .models import QueryRecord, QueryResult
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


def parse_current_identity(html: str, status_code: int) -> dict[str, str]:
    try:
        return _parse_current_identity(html, status_code)
    except IebContractError as error:
        raise ValueError(str(error)) from error


class PortalClient:
    """APP 适配器：组装逐人结果，所有生产调用由共享核心执行。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.ieb = IebSession(session, base_url, timeout)
        self.protocol = PersonnelProtocol(self.ieb)
        self.session = self.ieb.session
        self.request_lock = self.ieb.request_lock
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-qualification-query-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def cookies(self) -> dict[str, str]:
        return self.ieb.cookies

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
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "identity": identity,
        }

    def check_session(self) -> None:
        self.protocol.check_session()

    def require_credentials(self) -> None:
        self.ieb.require_credentials()

    def query(self, record: QueryRecord) -> QueryResult:
        self.require_credentials()
        result = self.protocol.request_all(record.employee_id, record.name)
        basic = result["basic"]
        assert isinstance(basic, dict)
        return QueryResult(
            page_name=str(result["pageName"]),
            technical_rows=result["technical"],  # type: ignore[arg-type]
            operation_rows=result["operation"],  # type: ignore[arg-type]
            basic_info=basic["基本信息"],  # type: ignore[arg-type]
            education_rows=basic["教育经历"],  # type: ignore[arg-type]
            work_rows=basic["工作经历"],  # type: ignore[arg-type]
            title_rows=basic["职称信息"],  # type: ignore[arg-type]
            family_rows=basic["家庭信息"],  # type: ignore[arg-type]
            training_record_rows=result["trainingRecords"],  # type: ignore[arg-type]
            training_experience_rows=result["trainingExperiences"],  # type: ignore[arg-type]
        )

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
    "BASIC_INFO_FIELDS",
    "OPERATION_HEADERS",
    "PortalClient",
    "PortalError",
    "PortalSessionExpired",
    "SECTION_FIELDS",
    "TECHNICAL_HEADERS",
    "TRAINING_EXPERIENCE_HEADERS",
    "TRAINING_RECORD_HEADERS",
    "build_employee_query_params",
    "parse_basic_payload",
    "parse_current_identity",
    "parse_detail_table",
    "parse_employee_identity",
    "parse_training_record_pages",
]
