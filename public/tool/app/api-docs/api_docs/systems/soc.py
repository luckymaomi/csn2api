from __future__ import annotations

import random
import re
import time
from threading import RLock
from typing import Callable

import requests
from bs4 import BeautifulSoup, Tag

from ..catalog import ApiCatalog, EndpointRecord
from ..credentials import all_credential_summary, format_all_credentials, parse_all_credentials
from .errors import ExecutionError, SessionExpiredError
from .session_keepalive import SessionKeepAlive


def random_keepalive_interval() -> int:
    return random.randint(30, 60)


def _parse_current_identity(html: str, status_code: int) -> dict[str, str] | None:
    """解析 SOC 外层页服务端欢迎语中的当前登录姓名。"""
    if status_code != 200:
        return None
    soup = BeautifulSoup(str(html or ""), "html.parser")
    node = soup.select_one("#checkout_soc, #checkout")
    text = node.get_text(" ", strip=True) if isinstance(node, Tag) else ""
    match = re.search(r"欢迎您\s*[，,]\s*([^\s]+)", text)
    name = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    if not name:
        return None
    return {"name": name}


class SocAdapter:
    """维护独立 SOC 会话，按 catalog 调试只读请求和明确授权写请求。"""

    def __init__(self, catalog: ApiCatalog, session_factory: Callable[[], requests.Session] = requests.Session, timeout_seconds: int = 30, keepalive_interval_factory: Callable[[], int] = random_keepalive_interval) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.session: requests.Session | None = None
        self.cookies: dict[str, str] = {}
        self.identity: dict[str, str] | None = None
        self.request_lock = RLock()
        self.keepalive = SessionKeepAlive(keepalive_interval_factory, timeout_seconds, "soc-cookie-keepalive")

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies = parse_all_credentials(source)
        session = self.session_factory()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        session.cookies.update(cookies)
        self.clear_credentials()
        with self.request_lock:
            self.session, self.cookies = session, cookies
        try:
            self._check_session()
            identity_request = self.catalog.get_session_request("soc", "identity")
            identity_response = self._request(
                str(identity_request.endpoint["method"]),
                identity_request.url,
                identity_request,
                {},
            )
            with self.request_lock:
                self.identity = _parse_current_identity(str(identity_response.text or ""), identity_response.status_code)
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
            self.identity = None
            if self.session is not None:
                self.session.close()
            self.session = None

    def session_status(self) -> dict[str, object]:
        with self.request_lock:
            return {**all_credential_summary(self.cookies), "identity": dict(self.identity) if self.identity else None, "keepAlive": self.keepalive.status(bool(self.cookies))}

    def execute(self, record: EndpointRecord, supplied: dict[str, object]) -> dict[str, object]:
        started = time.perf_counter()
        response = self._request(str(record.endpoint["method"]), record.url, record, supplied)
        try:
            payload = response.json()
            data = {"summary": {"responseKeys": list(payload) if isinstance(payload, dict) else []}, "tables": [], "json": payload}
        except ValueError:
            data = {"summary": {"bodyLength": len(response.text or "")}, "tables": []}
        return {
            "endpointId": record.full_id, "method": record.endpoint["method"], "status": response.status_code,
            "reason": response.reason, "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": str(response.url or record.url), "contentType": response.headers.get("Content-Type", ""),
            "headers": {name: value for name, value in response.headers.items() if name.lower() not in {"cookie", "set-cookie"}},
            "data": data, "body": str(response.text or ""),
        }

    def _request(self, method: str, url: str, record: EndpointRecord, supplied: dict[str, object]) -> requests.Response:
        with self.request_lock:
            if self.session is None or not self.cookies:
                raise SessionExpiredError("请先载入有效 SOC Cookie")
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
            headers = {
                str(item.get("name")): str(item.get("value"))
                for item in [*record.module.get("commonHeaders", []), *record.endpoint.get("headers", [])]
                if isinstance(item, dict) and item.get("name")
            }
            try:
                response = self.session.request(method, url, data=values if method == "POST" else None, params=values if method == "GET" else None, headers=headers, timeout=self.timeout_seconds, allow_redirects=False)
            except requests.RequestException as error:
                raise ExecutionError("连接 SOC 失败") from error
            if response.status_code in {301, 302, 303, 307, 308} or "doSsoProxy" in response.headers.get("Location", ""):
                self.clear_credentials()
                raise SessionExpiredError("SOC Cookie 已失效，请重新复制")
            if response.status_code != 200:
                raise ExecutionError(f"SOC 返回 HTTP {response.status_code}")
            return response

    def _check_session(self) -> None:
        request = self.catalog.get_session_request("soc", "keepAlive")
        self._request(str(request.endpoint["method"]), request.url, request, {})

    def close(self) -> None:
        self.clear_credentials()
