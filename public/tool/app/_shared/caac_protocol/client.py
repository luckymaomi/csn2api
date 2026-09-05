from __future__ import annotations

import json
import re
import time
from threading import RLock
from typing import Any, Callable
from urllib.parse import urljoin

import requests

from .credentials import parse_credentials


BASE_URL = "https://fsop.caac.gov.cn"
LIST_PATH = "/yzzzm/rygl/queryPilotByParamForPage"
DETAIL_PATH = "/yzzzm/rygl/queryPilotDetails"
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)
LIST_FILTER_NAMES = (
    "archiveNo",
    "idCode",
    "regionId",
    "nationality",
    "pilotname",
    "orgId",
    "licenseType",
    "medicalStatus",
    "copType",
)


class CaacProtocolError(RuntimeError):
    pass


class CaacSessionExpired(CaacProtocolError):
    pass


class CaacContractError(CaacProtocolError):
    pass


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _archive_key(value: object) -> str:
    text = _text(value)
    return (text.lstrip("0") or "0") if text.isdigit() else text


def _is_login_response(response: requests.Response) -> bool:
    location = str(response.headers.get("Location") or "").lower()
    text = str(response.text or "")[:5000].lower()
    return "login.jsp" in location or "/login" in location or "login.jsp" in text or "登录" in text and "password" in text


def _json(response: requests.Response) -> Any:
    try:
        return response.json()
    except (ValueError, json.JSONDecodeError) as error:
        raise CaacContractError("CAAC 接口未返回有效 JSON") from error


def build_list_form(
    page: int,
    rows: int = 10,
    filters: dict[str, object] | None = None,
) -> dict[str, str]:
    supplied = filters or {}
    form = {name: _text(supplied.get(name)) for name in LIST_FILTER_NAMES}
    form.update({"page": str(page), "rows": str(rows), "sort": "archiveNo", "order": "asc"})
    return form


def parse_pilot_page(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise CaacContractError("CAAC 列表响应缺少 rows 数组")
    try:
        total = int(payload.get("total"))
    except (TypeError, ValueError) as error:
        raise CaacContractError("CAAC 列表响应缺少有效 total") from error
    rows = [row for row in payload["rows"] if isinstance(row, dict)]
    if len(rows) != len(payload["rows"]):
        raise CaacContractError("CAAC 列表 rows 包含非对象记录")
    return rows, total


class CaacProtocolClient:
    def __init__(self, session: requests.Session | None = None, base_url: str = BASE_URL, timeout: int = 30) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_lock = RLock()
        self.cookies: dict[str, str] = {}
        self.session.headers.update({
            "User-Agent": DEFAULT_BROWSER_USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.base_url,
            "X-Requested-With": "XMLHttpRequest",
        })

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _post(self, path: str, data: dict[str, str]) -> requests.Response:
        with self.request_lock:
            try:
                response = self.session.request(
                    "POST",
                    self._url(path),
                    params={"ajaxPrefilter": str(int(time.time() * 1000))},
                    data=data,
                    headers={
                        "Referer": self._url("/yzzzm/rygl/pilotredirect"),
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise CaacProtocolError(f"CAAC 请求失败：{error.__class__.__name__}") from error
        if response.status_code in {301, 302, 303, 307, 308} or _is_login_response(response):
            raise CaacSessionExpired("CAAC 登录凭据已失效，请重新复制已登录请求")
        if response.status_code != 200:
            raise CaacProtocolError(f"CAAC HTTP 请求失败（状态 {response.status_code}）")
        return response

    def load_credentials(self, source: str) -> tuple[dict[str, str], int]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain="fsop.caac.gov.cn", path="/")
        try:
            _response, _rows, total = self.request_page(1, 1)
        except Exception:
            self.clear_credentials()
            raise
        self.cookies = cookies
        return cookies, total

    def request_page(
        self,
        page: int,
        page_size: int = 10,
        *,
        filters: dict[str, object] | None = None,
    ) -> tuple[requests.Response, list[dict[str, Any]], int]:
        response = self._post(LIST_PATH, build_list_form(page, page_size, filters))
        rows, total = parse_pilot_page(_json(response))
        return response, rows, total

    def fetch_page(
        self,
        page: int,
        page_size: int = 10,
        *,
        filters: dict[str, object] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        _response, rows, total = self.request_page(page, page_size, filters=filters)
        return rows, total

    def fetch_all_rows(
        self,
        page_size: int = 10,
        *,
        filters: dict[str, object] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return self._collect_rows(
            page_size,
            lambda page, size: self.fetch_page(page, size, filters=filters),
        )

    @staticmethod
    def _collect_rows(
        page_size: int,
        fetch_page: Callable[[int, int], tuple[list[dict[str, Any]], int]],
    ) -> tuple[list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        total: int | None = None
        page = 1
        while True:
            rows, reported_total = fetch_page(page, page_size)
            total = reported_total if total is None else total
            if reported_total != total:
                raise CaacContractError("CAAC 分页 total 在批次内发生变化")
            if not rows and len(records) < total:
                raise CaacContractError("CAAC 分页提前返回空页")
            for row in rows:
                pilot_id = _text(row.get("pilotId"))
                if not pilot_id:
                    raise CaacContractError("CAAC 列表记录缺少 pilotId")
                if pilot_id in seen:
                    raise CaacContractError("CAAC 分页返回重复 pilotId")
                seen.add(pilot_id)
                records.append(row)
            if len(records) >= total:
                break
            page += 1
        return records, int(total)

    def resolve_by_name(
        self,
        pilot_name: str,
        archive_no: str = "",
        page_size: int = 10,
        page_fetcher: Callable[[int, int], tuple[list[dict[str, Any]], int]] | None = None,
    ) -> tuple[dict[str, Any], int]:
        name = _text(pilot_name)
        archive = _text(archive_no)
        if not name:
            raise ValueError("请填写飞行员姓名")
        fetch = page_fetcher or (
            lambda page, size: self.fetch_page(
                page,
                size,
                filters={"pilotname": name, "archiveNo": archive},
            )
        )
        rows, _total = self._collect_rows(page_size, fetch)
        matches = [row for row in rows if _text(row.get("pilotname")) == name]
        if archive:
            matches = [row for row in matches if _archive_key(row.get("archiveNo")) == _archive_key(archive)]
        if not matches:
            raise CaacContractError("CAAC 姓名查询没有返回精确匹配的飞行员")
        if len(matches) != 1:
            suffix = "，请填写档案号继续筛选" if not archive else ""
            raise CaacContractError(f"CAAC 姓名查询精确匹配到 {len(matches)} 人{suffix}")
        return matches[0], len(rows)

    def request_detail(self, pilot_id: str) -> tuple[requests.Response, dict[str, Any]]:
        expected = _text(pilot_id)
        if not expected:
            raise ValueError("飞行员 ID 不能为空")
        response = self._post(DETAIL_PATH, {"pilotId": expected})
        payload = _json(response)
        if not isinstance(payload, dict) or _text(payload.get("pilotId")) != expected:
            raise CaacContractError("CAAC 详情无法按 pilotId 归属")
        return response, payload

    def fetch_detail(self, pilot_id: str) -> dict[str, Any]:
        _response, payload = self.request_detail(pilot_id)
        return payload

    def check_session(self) -> None:
        self.request_page(1, 1)

    def clear_credentials(self) -> None:
        self.cookies = {}
        try:
            self.session.cookies.clear()
        except AttributeError:
            pass

    def close(self) -> None:
        self.clear_credentials()
        self.session.close()
