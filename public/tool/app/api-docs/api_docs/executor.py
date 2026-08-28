from __future__ import annotations

from typing import Callable
from threading import Lock

import requests

from csn2api_runtime.credential_bundle import create_credential_bundle, parse_credential_bundle

from .catalog import ApiCatalog
from .systems.flight_portal import FlightPortalAdapter, random_keepalive_interval
from .systems.oa import OaAdapter
from .systems.soc import SocAdapter
from .systems.caac import CaacAdapter
from .systems.errors import ExecutionError, SessionExpiredError


class ApiExecutor:
    """按目录中的 systemId 将业务接口交给对应系统适配器。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.catalog = catalog
        self.adapters = {
            "flight-portal": FlightPortalAdapter(
                catalog,
                session_factory,
                timeout_seconds,
                keepalive_interval_factory,
            ),
            "oa": OaAdapter(
                catalog,
                session_factory,
                timeout_seconds,
                keepalive_interval_factory,
            ),
            "soc": SocAdapter(
                catalog,
                session_factory,
                timeout_seconds,
                keepalive_interval_factory,
            ),
            "caac-fsop": CaacAdapter(
                catalog,
                session_factory,
                timeout_seconds,
                keepalive_interval_factory,
            ),
        }
        self.credential_lock = Lock()
        self.credential_exports: dict[str, str] = {}

    @property
    def flight_portal(self) -> FlightPortalAdapter:
        return self.adapters["flight-portal"]

    def load_credentials(self, source: str, system_id: str = "flight-portal") -> dict[str, object]:
        with self.credential_lock:
            self.credential_exports.pop(system_id, None)
        result = self._adapter(system_id).load_credentials(source)
        credentials = str(result.get("credentials", "") or "")
        if not credentials:
            raise ValueError("系统没有返回可导出的规范化 Cookie")
        with self.credential_lock:
            self.credential_exports[system_id] = credentials
        return result

    def clear_credentials(self, system_id: str | None = None) -> None:
        targets = self.adapters.values() if system_id is None else [self._adapter(system_id)]
        for adapter in targets:
            adapter.clear_credentials()
        with self.credential_lock:
            if system_id is None:
                self.credential_exports.clear()
            else:
                self.credential_exports.pop(system_id, None)

    def export_credential_bundle(self) -> dict[str, object]:
        with self.credential_lock:
            credentials = {
                system_id: value
                for system_id, value in self.credential_exports.items()
                if self._adapter(system_id).session_status().get("ready") is True
            }
        return create_credential_bundle(credentials)

    def import_credential_bundle(self, payload: object) -> dict[str, object]:
        credentials = parse_credential_bundle(payload, allowed_system_ids=set(self.adapters))
        imported: list[str] = []
        failed: list[dict[str, str]] = []
        for system_id, value in credentials.items():
            try:
                self.load_credentials(value, system_id)
                imported.append(system_id)
            except Exception as error:
                failed.append({"systemId": system_id, "error": str(error)})
        return {
            "bundle": self.export_credential_bundle(),
            "imported": imported,
            "failed": failed,
            "sessions": self.all_session_statuses(),
        }

    def session_status(self, system_id: str = "flight-portal") -> dict[str, object]:
        return self._adapter(system_id).session_status()

    def all_session_statuses(self) -> dict[str, dict[str, object]]:
        return {
            system_id: adapter.session_status()
            for system_id, adapter in self.adapters.items()
        }

    def load_options(self, source: str) -> list[dict[str, str]]:
        return self.flight_portal.load_options(source)

    def execute(
        self,
        endpoint_id: str,
        supplied: dict[str, object],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        record = self.catalog.get_endpoint(endpoint_id)
        system_id = str(record.module.get("systemId", ""))
        adapter = self.adapters.get(system_id)
        if adapter is None:
            raise ExecutionError("接口所属系统没有本地执行器")
        if system_id == "oa":
            return adapter.execute(record, supplied, progress_callback)
        return adapter.execute(record, supplied)

    def close(self) -> None:
        for adapter in self.adapters.values():
            adapter.close()

    def _adapter(self, system_id: str) -> object:
        adapter = self.adapters.get(system_id)
        if adapter is None:
            raise ValueError("会话所属系统不存在")
        return adapter


__all__ = ["ApiExecutor", "ExecutionError", "SessionExpiredError"]
