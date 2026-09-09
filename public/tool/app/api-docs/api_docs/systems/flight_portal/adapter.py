from __future__ import annotations

import time
from typing import Callable

import requests

from ieb_protocol import (
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
)
from ieb_protocol.flight_stats import FlightStatsProtocol
from ieb_protocol.flight_detail import FlightDetailProtocol
from ieb_protocol.lock_protocol import LockProtocol
from ieb_protocol.personnel import PersonnelProtocol
from ieb_protocol.qualification_monitor import QualificationMonitorProtocol
from ieb_protocol.qualification_roster import QualificationRosterProtocol

from ...catalog import ApiCatalog, EndpointRecord
from ..errors import ExecutionError, SessionExpiredError
from ..session_keepalive import SessionKeepAlive
from . import flight_detail, flight_stats, lock_entry, personnel, qualification_monitor, qualification_roster
from .common import random_keepalive_interval, response_payload


class FlightPortalAdapter:
    """IEB 会话入口；领域请求和展示由各业务模块负责。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.ieb: IebSession | None = None
        self.session: requests.Session | None = None
        self.cookies: dict[str, str] = {}
        self.identity: dict[str, str] | None = None
        self.flight_stats: FlightStatsProtocol | None = None
        self.flight_detail: FlightDetailProtocol | None = None
        self.lock: LockProtocol | None = None
        self.personnel: PersonnelProtocol | None = None
        self.monitor: QualificationMonitorProtocol | None = None
        self.roster: QualificationRosterProtocol | None = None
        self.option_cache: dict[str, list[dict[str, str]]] = {}
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout_seconds,
            "flight-portal-cookie-keepalive",
        )

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        ieb = IebSession(self.session_factory(), timeout=self.timeout_seconds)
        cookies = ieb.load_credentials(source)
        self.ieb = ieb
        self.session = ieb.session  # API executor 的当前会话观察面。
        self.cookies = cookies
        self.flight_stats = FlightStatsProtocol(ieb)
        self.flight_detail = FlightDetailProtocol(ieb)
        self.lock = LockProtocol(ieb)
        self.personnel = PersonnelProtocol(ieb)
        self.monitor = QualificationMonitorProtocol(ieb)
        self.roster = QualificationRosterProtocol(ieb)
        try:
            _response, identity = self.flight_stats.validate_session()
        except Exception:
            self.clear_credentials()
            raise
        self.identity = identity
        ieb.identity = identity
        self.keepalive.record_success()
        self.keepalive.start(self._check_session)
        return {**self.session_status(), "credentials": format_credentials(cookies)}

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.cookies = {}
        self.identity = None
        self.option_cache = {}
        self.flight_stats = None
        self.flight_detail = None
        self.lock = None
        self.personnel = None
        self.monitor = None
        self.roster = None
        if self.ieb is not None:
            self.ieb.close()
        self.ieb = None
        self.session = None

    def session_status(self) -> dict[str, object]:
        return {
            **credential_summary(self.cookies),
            "ready": bool(self.cookies),
            "identity": dict(self.identity) if self.identity else None,
            "keepAlive": self.keepalive.status(bool(self.cookies)),
        }

    def load_options(self, source: str) -> list[dict[str, str]]:
        if source != "lock-types":
            raise ValueError("选项来源不存在")
        if source not in self.option_cache:
            _response, metadata = self._lock().request_metadata()
            self.option_cache[source] = lock_entry.option_rows(metadata)
        return self.option_cache[source]

    def execute(self, record: EndpointRecord, supplied: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        try:
            if record.full_id == "flight-stats.query":
                response, data = flight_stats.execute(record, supplied, self._flight_stats())
            elif record.full_id == "flight-detail.query-month":
                response, data = flight_detail.execute(record, supplied, self._flight_detail())
            elif record.full_id.startswith("personnel-info."):
                response, data = personnel.execute(record, supplied, self._personnel())
            elif record.module.get("id") == "qualification-monitor":
                response, data = qualification_monitor.execute(record, supplied, self._monitor())
            elif record.full_id.startswith("qualification-roster."):
                response, data = qualification_roster.execute(record, supplied, self._roster())
            elif record.full_id == "lock-entry.submit":
                self.load_options("lock-types")
                response, data = lock_entry.execute(
                    record,
                    supplied,
                    self._lock(),
                )
            elif record.full_id == "lock-entry.approve-pending":
                self.load_options("lock-types")
                return lock_entry.execute_approval(record, supplied, self._lock())
            else:
                raise ExecutionError("当前 IEB 系统不支持该业务接口")
        except IebSessionExpired as error:
            self.clear_credentials()
            self.keepalive.mark_expired()
            raise SessionExpiredError(str(error)) from error
        except IebProtocolError as error:
            raise ExecutionError(str(error)) from error
        return response_payload(record, response, started, data)

    def _flight_stats(self) -> FlightStatsProtocol:
        if self.flight_stats is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.flight_stats

    def _flight_detail(self) -> FlightDetailProtocol:
        if self.flight_detail is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.flight_detail

    def _personnel(self) -> PersonnelProtocol:
        if self.personnel is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.personnel

    def _lock(self) -> LockProtocol:
        if self.lock is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.lock

    def _monitor(self) -> QualificationMonitorProtocol:
        if self.monitor is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.monitor

    def _roster(self) -> QualificationRosterProtocol:
        if self.roster is None:
            raise SessionExpiredError("请先载入有效 Cookie")
        return self.roster

    def _check_session(self) -> None:
        try:
            self._flight_stats().check_session()
        except IebSessionExpired as error:
            self.clear_credentials()
            raise SessionExpiredError(str(error)) from error

    def close(self) -> None:
        self.clear_credentials()
