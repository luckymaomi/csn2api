"""OA 纯 HTTP 会话、待办分页和公文已阅契约。"""

from __future__ import annotations

import copy
from datetime import datetime
from threading import RLock
from typing import Callable

import requests

from .credentials import (
    credential_summary,
    format_all_credentials,
    parse_browser_headers,
    parse_credentials,
    parse_waiting_payload,
)
from .models import ELIGIBLE_CATEGORY, ScanSnapshot, WaitingRecord
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


BASE_URL = "https://work.csair.com"
USER_INFO_PATH = "/oai/work/login/userInfo"
WAITING_QUERY_PATH = "/oai/work/box/query/waiting"
HAVE_READ_PATH = "/oai/doc/pc/form/sw/haveRead"
PAGE_SIZE = 100
VERIFY_TIMEOUT = (5, 10)
WAITING_ROW_KEYS = ("resultMyBoxItems", "resultList", "rows", "records", "list", "content", "items")
WAITING_TOTAL_KEYS = ("totalRecordCount", "totalCount", "total", "recordsTotal", "totalElements")


class PortalError(RuntimeError):
    pass


class PortalBusinessError(PortalError):
    """OA 返回 HTTP 成功但业务码不是 200。"""


class PortalSessionExpired(PortalError):
    pass


def _business_payload(response: object, action: str) -> dict[str, object]:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code in {301, 302, 303, 307, 308}:
        raise PortalSessionExpired(
            "OA 将请求重定向到登录流程，请从 /oai/work/box/query/waiting 重新 Copy as cURL"
        )
    if status_code != 200:
        raise PortalError(f"{action}返回 HTTP {status_code}")
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except (ValueError, TypeError) as error:
        raise PortalError(f"{action}没有返回 JSON") from error
    if not isinstance(payload, dict):
        raise PortalError(f"{action}响应结构不是对象")
    code = str(payload.get("code") or "")
    if code == "301":
        raise PortalSessionExpired(
            "OA 登录会话已失效，请从 /oai/work/box/query/waiting 重新 Copy as cURL"
        )
    if code != "200":
        raise PortalBusinessError(f"{action}业务码不是 200")
    return payload


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        parsed = int(value)
        return parsed if parsed >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _find_page_contract(value: object) -> tuple[list[object], int | None] | None:
    if not isinstance(value, dict):
        return None
    for row_key in WAITING_ROW_KEYS:
        if row_key not in value:
            continue
        rows = value.get(row_key)
        total = next(
            (_non_negative_integer(value.get(key)) for key in WAITING_TOTAL_KEYS if key in value),
            None,
        )
        if isinstance(rows, list):
            return rows, total
        if rows is None and total == 0:
            return [], 0
    for candidate in value.values():
        found = _find_page_contract(candidate)
        if found is not None:
            return found
    return None


def _find_total(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in WAITING_TOTAL_KEYS:
        if key in value:
            parsed = _non_negative_integer(value.get(key))
            if parsed is not None:
                return parsed
    for candidate in value.values():
        found = _find_total(candidate)
        if found is not None:
            return found
    return None


class PortalClient:
    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.request_lock = RLock()
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout_seconds,
            "http-oa-read-cookie-keepalive",
        )
        self._session: requests.Session | object | None = None
        self._waiting_payload_template: dict[str, object] | None = None
        self.copyable_credentials = ""
        self.verified_at = ""

    @staticmethod
    def _configure_session(
        session: object,
        cookies: dict[str, str],
        browser_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/oaw/work/my-dealt-with/schedule-list?sourceType=wait",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        headers.update(browser_headers or {})
        session.headers.update(headers)  # type: ignore[attr-defined]
        for name, value in cookies.items():
            session.cookies.set(name, value, domain="work.csair.com", path="/")  # type: ignore[attr-defined]

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies = parse_credentials(source)
        browser_headers = parse_browser_headers(source)
        waiting_payload = parse_waiting_payload(source)
        self.clear_credentials()
        session = self.session_factory()
        self._configure_session(session, cookies, browser_headers)
        try:
            response = session.get(  # type: ignore[attr-defined]
                f"{BASE_URL}{USER_INFO_PATH}",
                timeout=VERIFY_TIMEOUT,
                allow_redirects=False,
            )
            _business_payload(response, "验证 OA 凭据")
        except requests.Timeout as error:
            session.close()  # type: ignore[attr-defined]
            raise PortalError("验证 OA 凭据超时，请确认已连接内网并重新复制当前 Cookie") from error
        except requests.RequestException as error:
            session.close()  # type: ignore[attr-defined]
            raise PortalError("连接 OA 失败") from error
        except Exception:
            session.close()  # type: ignore[attr-defined]
            raise
        with self.request_lock:
            self._session = session
            self._waiting_payload_template = waiting_payload
            self.copyable_credentials = format_all_credentials(cookies)
            self.verified_at = datetime.now().isoformat(timespec="seconds")
        return {**credential_summary(cookies), "verifiedAt": self.verified_at}

    def _active_session(self) -> object:
        if self._session is None:
            raise PortalSessionExpired("请先验证 OA 登录凭据")
        return self._session

    def check_session(self) -> None:
        with self.request_lock:
            try:
                response = self._active_session().get(  # type: ignore[attr-defined]
                    f"{BASE_URL}{USER_INFO_PATH}",
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise PortalError("OA 保活请求失败") from error
            _business_payload(response, "验证 OA 凭据")

    def _waiting_payload(self, offset_page_index: int) -> dict[str, object]:
        payload = copy.deepcopy(self._waiting_payload_template) if self._waiting_payload_template else {
            "offsetPageIndex": offset_page_index,
            "pageMode": "page",
            "resultCountPerPage": PAGE_SIZE,
        }
        # /dashboard 的 moduleMainCategoryId=-5 只代表当前页面筛选，不是全部待办。
        # 扫描工作台需要同一接口的全量待办，因此移除该页面筛选并保留其余动态字段。
        payload.pop("moduleMainCategoryId", None)
        payload["offsetPageIndex"] = offset_page_index
        payload["resultCountPerPage"] = PAGE_SIZE
        return payload

    def _query_waiting_page(self, offset_page_index: int) -> tuple[list[WaitingRecord], int | None]:
        with self.request_lock:
            try:
                response = self._active_session().post(  # type: ignore[attr-defined]
                    f"{BASE_URL}{WAITING_QUERY_PATH}",
                    json=self._waiting_payload(offset_page_index),
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise PortalError("查询 OA 待办失败") from error
        payload = _business_payload(response, "查询 OA 待办")
        contract = _find_page_contract(payload)
        if contract is None:
            raise PortalError("待办响应中没有可识别的记录数组")
        rows, local_total = contract
        total = local_total if local_total is not None else _find_total(payload)
        try:
            records = [WaitingRecord.from_payload(row) for row in rows]
        except ValueError as error:
            raise PortalError(str(error)) from error
        return records, total

    def scan_waiting(self) -> ScanSnapshot:
        records: list[WaitingRecord] = []
        seen_keys: set[tuple[str, str]] = set()
        page_index = 0
        while True:
            page_records, total = self._query_waiting_page(page_index)
            if not page_records:
                break
            added = 0
            for record in page_records:
                key = (record.file_id, record.step_item_id)
                if key not in seen_keys:
                    seen_keys.add(key)
                    records.append(record)
                    added += 1
            if total is not None and len(records) >= total:
                break
            if len(page_records) < PAGE_SIZE or added == 0:
                break
            page_index += 1
        return ScanSnapshot.from_records(records, total=len(records))

    def mark_read(self, record: WaitingRecord) -> None:
        if record.category != ELIGIBLE_CATEGORY:
            raise PortalError("不同模块不允许调用公文已阅接口")
        request_body = {
            "approveOpinionType": None,
            "approveOpinionContent": None,
            "docId": record.file_id,
            "docType": record.file_type_id,
            "flowStepId": record.step_item_id,
        }
        with self.request_lock:
            try:
                response = self._active_session().post(  # type: ignore[attr-defined]
                    f"{BASE_URL}{HAVE_READ_PATH}",
                    json=request_body,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise PortalError("提交 OA 已阅失败") from error
        _business_payload(response, "提交 OA 已阅")

    def invalidate_credentials(self) -> None:
        with self.request_lock:
            if self._session is not None:
                self._session.close()  # type: ignore[attr-defined]
                self._session = None
            self._waiting_payload_template = None
            self.copyable_credentials = ""
            self.verified_at = ""

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.clear_credentials()
