from __future__ import annotations

from typing import Callable

import requests

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

    @property
    def flight_portal(self) -> FlightPortalAdapter:
        return self.adapters["flight-portal"]

    def load_credentials(self, source: str, system_id: str = "flight-portal") -> dict[str, object]:
        return self._adapter(system_id).load_credentials(source)

    def clear_credentials(self, system_id: str | None = None) -> None:
        targets = self.adapters.values() if system_id is None else [self._adapter(system_id)]
        for adapter in targets:
            adapter.clear_credentials()

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
