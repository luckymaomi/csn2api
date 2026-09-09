from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from ieb_protocol import (
    BASE_URL,
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    format_credentials,
)
from ieb_protocol.lock_models import (
    EmployeeIdentity,
    LockSubmission,
    LockTypeMetadata,
    PortalMetadata,
    SubmitResult,
)
from ieb_protocol.lock_protocol import LockProtocol, random_value
from ieb_protocol.lock_submission import build_submit_form, resolve_lock_reason

from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = IebProtocolError
PortalSessionExpired = IebSessionExpired


class PortalClient:
    """APP 适配器：把归一后的 Excel 记录映射到共享锁班协议。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.ieb = IebSession(session, base_url, timeout)
        self.protocol = LockProtocol(self.ieb)
        self.session = self.ieb.session
        self.request_lock = self.ieb.request_lock
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-lock-entry-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def metadata(self) -> PortalMetadata | None:
        return self.protocol.metadata

    @metadata.setter
    def metadata(self, value: PortalMetadata | None) -> None:
        self.protocol.metadata = value

    @property
    def identity(self) -> dict[str, str] | None:
        return self.ieb.identity

    def load_credentials(self, source: str) -> PortalMetadata:
        self.clear_credentials()
        cookies = self.ieb.load_credentials(source)
        try:
            metadata, _identity = self.protocol.load_metadata()
        except Exception:
            self.ieb.clear_credentials()
            raise
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return metadata

    def check_session(self) -> None:
        self.protocol.check_session()

    def invalidate_credentials(self) -> None:
        self.protocol.metadata = None
        self.copyable_credentials = ""
        self.verified_at = ""
        self.ieb.clear_credentials()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def require_metadata(self) -> PortalMetadata:
        return self.protocol.require_metadata()

    def validate_employee(self, employee_id: str) -> EmployeeIdentity:
        return self.protocol.validate_employee(employee_id)

    def resolve_reason(self, record: dict[str, object], common_reason: str) -> str:
        metadata = self.require_metadata()
        item = metadata.lock_types.get(str(record.get("请假类型", "")))
        if item is None:
            raise PortalError("当前记录的锁班类型不在动态类型列表中")
        return resolve_lock_reason(metadata, item, record.get("备注"), common_reason)

    @staticmethod
    def _submission(record: dict[str, object], identity: EmployeeIdentity, reason: str) -> LockSubmission:
        return LockSubmission(
            employee_id=identity.employee_id,
            lock_type=str(record.get("请假类型", "")),
            time_mode=int(record.get("时间模式", 1)),
            start_date=str(record.get("开始日期", "")),
            end_date=str(record.get("结束日期", "")),
            start_time=str(record.get("开始时间", "")),
            end_time=str(record.get("结束时间", "")),
            month=str(record.get("月份", "")),
            days=tuple(int(value) for value in record.get("日期列表", [])),
            reason=reason,
        )

    def build_submit_data(
        self,
        record: dict[str, object],
        identity: EmployeeIdentity,
        item: LockTypeMetadata,
        reason: str,
    ) -> list[tuple[str, str]]:
        return build_submit_form(self._submission(record, identity, reason), identity, item, random_value)

    def submit(self, body: list[tuple[str, str]]) -> SubmitResult:
        _response, result = self.protocol.submit_form(body)
        return result

    def attribute_submit_result(
        self,
        result: SubmitResult,
        record: dict[str, object],
        identity: EmployeeIdentity,
    ) -> tuple[list[dict[str, str]], str]:
        return self.protocol.attribute_result(result, self._submission(record, identity, ""), identity)

    def attribute_conflict_result(
        self,
        result: SubmitResult,
        record: dict[str, object],
        identity: EmployeeIdentity,
    ) -> tuple[list[dict[str, str]], str]:
        return self.protocol.attribute_result(
            result,
            self._submission(record, identity, ""),
            identity,
            conflicts=True,
        )

    def query_records(self, employee_id: str, status: str) -> list[dict[str, str]]:
        return self.protocol.query_records(employee_id, status)

    def perform_state_action(self, action: str, rows: list[dict[str, str]], reason: str) -> str:
        return self.protocol.perform_state_action(action, rows, reason)

    def approve_records(self, rows: list[dict[str, str]], reason: str) -> str:
        return self.protocol.approve_records(rows, reason)

    def close(self) -> None:
        self.keepalive.stop()
        self.ieb.close()
