from __future__ import annotations

import time
from typing import Callable

import requests

from soc_protocol import (
    FLIGHTS_PATH,
    REASONS_PATH,
    STAFF_VALIDATE_PATH,
    SUBMIT_PATH,
    SUGGEST_PATH,
    SocProtocolClient,
    SocProtocolError,
    SocSessionExpired,
    credential_summary,
    format_credentials,
    parse_flight_options,
    parse_station_suggestions,
    parse_submit_outcome,
)

from ...catalog import ApiCatalog, EndpointRecord
from ..errors import ExecutionError, SessionExpiredError
from ..session_keepalive import SessionKeepAlive
from .presentation import present_flights, present_json, present_submit, present_suggestions


class SocAdapter:
    """SOC API 文档入口；生产请求由共享 core 执行。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = lambda: 45,
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.protocol: SocProtocolClient | None = None
        self.cookies: dict[str, str] = {}
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory, timeout_seconds, "soc-cookie-keepalive",
        )

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        protocol = SocProtocolClient(self.session_factory, timeout_seconds=self.timeout_seconds)
        try:
            cookies, _identity = protocol.load_credentials(source)
        except SocSessionExpired as error:
            protocol.close()
            raise SessionExpiredError(str(error)) from error
        except SocProtocolError as error:
            protocol.close()
            raise ExecutionError(str(error)) from error
        self.protocol, self.cookies = protocol, cookies
        self.keepalive.record_success()
        self.keepalive.start(self._check_session)
        return {**self.session_status(), "credentials": format_credentials(cookies)}

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.cookies = {}
        if self.protocol is not None:
            self.protocol.close()
        self.protocol = None

    def session_status(self) -> dict[str, object]:
        return {
            **credential_summary(self.cookies),
            "identity": dict(self.protocol.identity) if self.protocol and self.protocol.identity else None,
            "keepAlive": self.keepalive.status(bool(self.cookies)),
        }

    def _core(self) -> SocProtocolClient:
        if self.protocol is None or not self.cookies:
            raise SessionExpiredError("请先载入有效 SOC Cookie")
        return self.protocol

    def _call(self, operation: Callable[[], object]) -> object:
        try:
            return operation()
        except SocSessionExpired as error:
            self.clear_credentials()
            self.keepalive.mark_expired()
            raise SessionExpiredError(str(error)) from error
        except SocProtocolError as error:
            raise ExecutionError(str(error)) from error

    @staticmethod
    def _form(record: EndpointRecord, supplied: dict[str, object]) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        definitions = record.endpoint.get("parameters", [])
        if not isinstance(definitions, list):
            return values
        for item in definitions:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            value = item.get("default", "") if item.get("fixed") else supplied.get(name, item.get("default", ""))
            if isinstance(value, list):
                values.extend((name, str(part)) for part in value)
            elif value is not None and (str(value) or item.get("includeWhenEmpty")):
                values.append((name, str(value)))
        return values

    def execute(self, record: EndpointRecord, supplied: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        form = self._form(record, supplied)
        path_by_endpoint = {
            "soc-positioning.station-suggest": SUGGEST_PATH,
            "soc-positioning.apply-reasons": REASONS_PATH,
            "soc-positioning.flights": FLIGHTS_PATH,
            "soc-positioning.staff-validation": STAFF_VALIDATE_PATH,
            "soc-positioning.submit": SUBMIT_PATH,
        }
        path = path_by_endpoint.get(record.full_id)
        if path is None:
            raise ExecutionError("当前 SOC 系统不支持该业务接口")
        response, payload = self._call(
            lambda: self._core().raw_json(path, form, str(record.endpoint.get("name") or "SOC 请求"))
        )  # type: ignore[misc]
        if record.full_id == "soc-positioning.station-suggest":
            data = present_suggestions(parse_station_suggestions(payload))
        elif record.full_id == "soc-positioning.flights":
            data = present_flights(parse_flight_options(payload))
        elif record.full_id == "soc-positioning.submit":
            data = present_submit(payload, parse_submit_outcome(payload))
        else:
            data = present_json(payload)
        return {
            "endpointId": record.full_id,
            "method": record.endpoint["method"],
            "status": response.status_code,
            "reason": response.reason,
            "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": str(response.url or record.url),
            "contentType": response.headers.get("Content-Type", ""),
            "headers": {
                name: value for name, value in response.headers.items()
                if name.lower() not in {"cookie", "set-cookie"}
            },
            "data": data,
            "body": str(response.text or ""),
        }

    def _check_session(self) -> None:
        self._call(lambda: self._core().check_session())

    def close(self) -> None:
        self.clear_credentials()


__all__ = ["SocAdapter"]
