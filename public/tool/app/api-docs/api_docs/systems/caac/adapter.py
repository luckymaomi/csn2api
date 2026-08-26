from __future__ import annotations

import time
from typing import Callable

import requests

from caac_protocol import (
    CaacProtocolClient,
    CaacProtocolError,
    CaacSessionExpired,
    credential_summary,
    format_credentials,
)

from ...catalog import ApiCatalog, EndpointRecord
from ..errors import ExecutionError, SessionExpiredError
from ..session_keepalive import SessionKeepAlive
from .presentation import parse_pilot_detail, parse_pilot_list


class CaacAdapter:
    """把共享 CAAC protocol core 暴露为 API 文档单次调试入口。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] | None = None,
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.protocol: CaacProtocolClient | None = None
        self.cookies: dict[str, str] = {}
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory or (lambda: 45), timeout_seconds, "caac-cookie-keepalive",
        )

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        protocol = CaacProtocolClient(self.session_factory(), timeout=self.timeout_seconds)
        try:
            cookies, _total = protocol.load_credentials(source)
        except CaacSessionExpired as error:
            protocol.close()
            raise SessionExpiredError(str(error)) from error
        except CaacProtocolError as error:
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
            **credential_summary(self.cookies), "ready": bool(self.cookies), "identity": None,
            "keepAlive": self.keepalive.status(bool(self.cookies)),
        }

    def _core(self) -> CaacProtocolClient:
        if self.protocol is None or not self.cookies:
            raise SessionExpiredError("请先载入有效 CAAC Cookie")
        return self.protocol

    def _call(self, operation: Callable[[], object]) -> object:
        try:
            return operation()
        except CaacSessionExpired as error:
            self.clear_credentials()
            self.keepalive.mark_expired()
            raise SessionExpiredError(str(error)) from error
        except CaacProtocolError as error:
            raise ExecutionError(str(error)) from error

    def execute(self, record: EndpointRecord, supplied: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        if record.full_id == "caac-pilot-export.pilot-list":
            try:
                page = int(supplied.get("page") or 1)
                page_size = int(supplied.get("rows") or 10)
            except (TypeError, ValueError) as error:
                raise ValueError("页码和页大小必须是整数") from error
            response, rows, total = self._call(
                lambda: self._core().request_page(page, page_size, filters=supplied)
            )  # type: ignore[misc]
            data = parse_pilot_list({"total": total, "rows": rows}, {**supplied, "page": page, "rows": page_size})
        elif record.full_id == "caac-pilot-export.pilot-detail":
            pilot_name = str(supplied.get("pilotname") or "").strip()
            archive_no = str(supplied.get("archiveNo") or "").strip()
            listing, scanned = self._call(
                lambda: self._core().resolve_by_name(pilot_name, archive_no)
            )  # type: ignore[misc]
            assert isinstance(listing, dict)
            response, payload = self._call(
                lambda: self._core().request_detail(str(listing.get("pilotId") or ""))
            )  # type: ignore[misc]
            data = parse_pilot_detail(payload, {"matchedListRows": 1, "scannedListRows": scanned})
        else:
            raise ExecutionError("当前 CAAC 系统不支持该业务接口")
        return {
            "endpointId": record.full_id, "method": record.endpoint["method"],
            "status": response.status_code, "reason": response.reason,
            "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": str(response.url or record.url),
            "contentType": response.headers.get("Content-Type", ""),
            "headers": {
                name: value for name, value in response.headers.items()
                if name.lower() not in {"cookie", "set-cookie"}
            },
            "data": data, "body": str(response.text or ""),
        }

    def _check_session(self) -> None:
        self._call(lambda: self._core().check_session())

    def close(self) -> None:
        self.clear_credentials()


__all__ = ["CaacAdapter"]
