from __future__ import annotations

import copy
from threading import RLock
from typing import Callable
from urllib.parse import urljoin

import requests

from .contract import (
    OaContractError,
    OaProtocolError,
    OaSessionExpired,
    find_page_contract,
    find_total,
    parse_business_payload,
    parse_identity,
)
from .credentials import parse_browser_headers, parse_credentials, parse_waiting_template
from .models import ELIGIBLE_CATEGORY, ScanSnapshot, WaitingRecord


BASE_URL = "https://work.csair.com"
USER_INFO_PATH = "/oai/work/login/userInfo"
WAITING_QUERY_PATH = "/oai/work/box/query/waiting"
HAVE_READ_PATH = "/oai/doc/pc/form/sw/haveRead"
PAGE_SIZE = 100
VERIFY_TIMEOUT = (5, 10)
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)


class OaProtocolClient:
    """OA 会话、动态分页与单条已阅生产协议。"""

    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        base_url: str = BASE_URL,
        timeout_seconds: int = 30,
    ) -> None:
        self.session_factory = session_factory
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.request_lock = RLock()
        self.session: requests.Session | object | None = None
        self.cookies: dict[str, str] = {}
        self.identity: dict[str, str] | None = None
        self.waiting_template: dict[str, object] | None = None

    def url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def load_credentials(self, source: str) -> tuple[dict[str, str], dict[str, str]]:
        cookies = parse_credentials(source)
        session = self.session_factory()
        headers = {
            "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/oaw/work/my-dealt-with/schedule-list?sourceType=wait",
            "User-Agent": DEFAULT_BROWSER_USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }
        headers.update(parse_browser_headers(source))
        session.headers.update(headers)  # type: ignore[attr-defined]
        for name, value in cookies.items():
            session.cookies.set(name, value, domain="work.csair.com", path="/")  # type: ignore[attr-defined]
        self.clear_credentials()
        self.session, self.cookies = session, cookies
        self.waiting_template = parse_waiting_template(source)
        try:
            _response, identity = self.fetch_identity(verify=True)
        except Exception:
            self.clear_credentials()
            raise
        self.identity = identity
        return cookies, identity

    def require_session(self) -> object:
        if self.session is None or not self.cookies:
            raise OaSessionExpired("请先验证 OA 登录凭据")
        return self.session

    def request(self, method: str, path: str, *, action: str, timeout: object | None = None, **kwargs: object) -> tuple[object, dict[str, object]]:
        with self.request_lock:
            session = self.require_session()
            try:
                response = session.request(  # type: ignore[attr-defined]
                    method, self.url(path), timeout=timeout or self.timeout_seconds,
                    allow_redirects=False, **kwargs,
                )
            except requests.Timeout as error:
                raise OaProtocolError(f"{action}超时") from error
            except requests.RequestException as error:
                raise OaProtocolError(f"{action}连接失败") from error
        try:
            payload = parse_business_payload(response, action)
        except OaSessionExpired:
            self.clear_credentials()
            raise
        return response, payload

    def fetch_identity(self, *, verify: bool = False) -> tuple[object, dict[str, str]]:
        response, payload = self.request("GET", USER_INFO_PATH, action="验证 OA 凭据", timeout=VERIFY_TIMEOUT if verify else None)
        identity = parse_identity(payload)
        self.identity = identity
        return response, identity

    def check_session(self) -> None:
        self.fetch_identity()

    def waiting_payload(self, page_index: int) -> dict[str, object]:
        payload = copy.deepcopy(self.waiting_template) if self.waiting_template else {}
        payload.pop("moduleMainCategoryId", None)
        payload.update({"offsetPageIndex": page_index, "pageMode": "page", "resultCountPerPage": PAGE_SIZE})
        return payload

    def request_waiting_page(self, page_index: int) -> tuple[object, list[WaitingRecord], int | None]:
        response, payload = self.request(
            "POST", WAITING_QUERY_PATH, action="查询 OA 待办", json=self.waiting_payload(page_index),
        )
        contract = find_page_contract(payload)
        if contract is None:
            raise OaContractError("待办响应中没有可识别的记录数组")
        rows, local_total = contract
        total = local_total if local_total is not None else find_total(payload)
        try:
            records = [WaitingRecord.from_payload(row) for row in rows]
        except ValueError as error:
            raise OaContractError(str(error)) from error
        return response, records, total

    def scan_waiting(self) -> ScanSnapshot:
        records: list[WaitingRecord] = []
        seen: set[tuple[str, str]] = set()
        page = 0
        observed_total: int | None = None
        while True:
            _response, page_records, total = self.request_waiting_page(page)
            if total is not None:
                observed_total = total
            if not page_records:
                break
            added = 0
            for record in page_records:
                key = (record.file_id, record.step_item_id)
                if key not in seen:
                    seen.add(key); records.append(record); added += 1
            if observed_total is not None and len(records) >= observed_total:
                break
            if len(page_records) < PAGE_SIZE or added == 0:
                break
            page += 1
        if observed_total is not None and len(records) < observed_total:
            raise OaContractError("OA 待办分页提前结束，未达到服务端总数")
        return ScanSnapshot(records, len(records))

    def mark_read(self, record: WaitingRecord) -> object:
        if record.category != ELIGIBLE_CATEGORY:
            raise OaContractError("不同模块不允许调用公文已阅接口")
        response, _payload = self.request(
            "POST", HAVE_READ_PATH, action="提交 OA 已阅",
            json={"approveOpinionType": None, "approveOpinionContent": None, "docId": record.file_id, "docType": record.file_type_id, "flowStepId": record.step_item_id},
        )
        return response

    def clear_credentials(self) -> None:
        with self.request_lock:
            if self.session is not None:
                self.session.close()  # type: ignore[attr-defined]
            self.session = None
            self.cookies = {}
            self.identity = None
            self.waiting_template = None

    def close(self) -> None:
        self.clear_credentials()
