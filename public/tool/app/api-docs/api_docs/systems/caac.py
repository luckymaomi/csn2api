from __future__ import annotations

import re
import time
from threading import RLock
from typing import Callable

import requests

from ..catalog import ApiCatalog, EndpointRecord
from ..credentials import all_credential_summary, format_all_credentials, parse_all_credentials
from .errors import ExecutionError, SessionExpiredError
from .session_keepalive import SessionKeepAlive

REQUIRED_COOKIES = ("yzzzm", "JSESSIONID", "home")


def _decode_shell_value(value: str) -> str:
    def unicode_value(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))
    return re.sub(r"\\u([0-9a-fA-F]{4})", unicode_value, value).replace("\\_", "_")


class CaacAdapter:
    """维护独立 CAAC 会话，只执行目录内两个飞行员只读端点。"""

    def __init__(self, catalog: ApiCatalog, session_factory: Callable[[], requests.Session] = requests.Session, timeout_seconds: int = 30, keepalive_interval_factory: Callable[[], int] | None = None) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.session: requests.Session | None = None
        self.cookies: dict[str, str] = {}
        self.request_lock = RLock()
        interval = keepalive_interval_factory or (lambda: 45)
        self.keepalive = SessionKeepAlive(interval, timeout_seconds, "caac-cookie-keepalive")

    def load_credentials(self, source: str) -> dict[str, object]:
        parsed = parse_all_credentials(source)
        cookies = {name: _decode_shell_value(value) for name, value in parsed.items()}
        missing = [name for name in REQUIRED_COOKIES if not cookies.get(name)]
        if missing:
            raise ValueError(f"CAAC 登录凭据缺少 Cookie：{', '.join(missing)}")
        session = self.session_factory()
        session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"})
        session.cookies.update(cookies)
        self.clear_credentials()
        with self.request_lock:
            self.session, self.cookies = session, cookies
        try:
            self._check_session()
        except Exception:
            self.clear_credentials()
            raise
        self.keepalive.record_success()
        self.keepalive.start(self._check_session)
        return {**self.session_status(), "credentials": format_all_credentials(cookies)}

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        with self.request_lock:
            self.cookies = {}
            if self.session is not None:
                self.session.close()
            self.session = None

    def session_status(self) -> dict[str, object]:
        with self.request_lock:
            return {**all_credential_summary(self.cookies), "identity": None, "keepAlive": self.keepalive.status(bool(self.cookies))}

    @staticmethod
    def _parameters(record: EndpointRecord, supplied: dict[str, object]) -> list[tuple[str, str]]:
        values: list[tuple[str, str]] = []
        definitions = record.endpoint.get("parameters", [])
        if isinstance(definitions, list):
            for item in definitions:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", ""))
                value = item.get("default", "") if item.get("fixed") else supplied.get(name, item.get("default", ""))
                if value is not None and (str(value) or item.get("includeWhenEmpty")):
                    values.append((name, str(value)))
        return values

    def _request(self, record: EndpointRecord, supplied: dict[str, object]) -> requests.Response:
        with self.request_lock:
            if self.session is None or not self.cookies:
                raise SessionExpiredError("请先载入有效 CAAC Cookie")
            url = record.url.replace("{timestamp}", str(int(time.time() * 1000)))
            headers = {
                str(item.get("name")): str(item.get("value"))
                for item in [*record.module.get("commonHeaders", []), *record.endpoint.get("headers", [])]
                if isinstance(item, dict) and item.get("name")
            }
            try:
                response = self.session.request(str(record.endpoint["method"]), url, data=self._parameters(record, supplied), headers=headers, timeout=self.timeout_seconds, allow_redirects=False)
            except requests.RequestException as error:
                raise ExecutionError("连接 CAAC 失败") from error
            location = str(response.headers.get("Location") or "")
            if response.status_code in {301, 302, 303, 307, 308} or "login.jsp" in location:
                self.clear_credentials()
                raise SessionExpiredError("CAAC Cookie 已失效，请重新复制")
            if response.status_code != 200:
                raise ExecutionError(f"CAAC 返回 HTTP {response.status_code}")
            return response

    @staticmethod
    def _payload(response: requests.Response, record: EndpointRecord, supplied: dict[str, object]) -> object:
        try:
            payload = response.json()
        except ValueError as error:
            raise ExecutionError("CAAC 接口未返回有效 JSON") from error
        if "queryPilotByParamForPage" in str(record.endpoint.get("path", "")):
            if not isinstance(payload, dict) or not isinstance(payload.get("total"), (int, float)) or not isinstance(payload.get("rows"), list):
                raise ExecutionError("CAAC 列表响应结构异常")
        if record.full_id == "caac-pilot-export.pilot-detail":
            expected = str(supplied.get("pilotId") or "")
            if not isinstance(payload, dict) or str(payload.get("pilotId") or "") != expected:
                raise ExecutionError("CAAC 详情无法按 pilotId 归属")
        return payload

    def execute(self, record: EndpointRecord, supplied: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        response = self._request(record, supplied)
        payload = self._payload(response, record, supplied)
        return {
            "endpointId": record.full_id, "method": record.endpoint["method"], "status": response.status_code,
            "reason": response.reason, "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": str(response.url or record.url), "contentType": response.headers.get("Content-Type", ""),
            "headers": {name: value for name, value in response.headers.items() if name.lower() not in {"cookie", "set-cookie"}},
            "data": {"summary": {"responseKeys": list(payload) if isinstance(payload, dict) else []}, "tables": [], "json": payload},
            "body": str(response.text or ""),
        }

    def _check_session(self) -> None:
        record = self.catalog.get_session_request("caac-fsop", "keepAlive")
        response = self._request(record, {})
        self._payload(response, record, {})

    def close(self) -> None:
        self.clear_credentials()


__all__ = ["CaacAdapter"]
