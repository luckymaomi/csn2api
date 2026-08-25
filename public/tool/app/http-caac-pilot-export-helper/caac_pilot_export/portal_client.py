from __future__ import annotations

import json
import time
from threading import RLock
from typing import Any, Callable
from urllib.parse import urljoin

import requests

from .credentials import credential_summary, format_credentials, parse_credentials
from .models import PilotRecord, PilotOutcome
from .session_keepalive import SessionKeepAlive, random_keepalive_interval

BASE_URL = "https://fsop.caac.gov.cn"
LIST_PATH = "/yzzzm/rygl/queryPilotByParamForPage"
DETAIL_PATH = "/yzzzm/rygl/queryPilotDetails"


class PortalError(RuntimeError):
    pass


class PortalSessionExpired(PortalError):
    pass


class PortalContractError(PortalError):
    pass


def _is_login_response(response: requests.Response) -> bool:
    location = str(response.headers.get("Location") or "").lower()
    text = str(response.text or "")[:5000].lower()
    return "login.jsp" in location or "/login" in location or "login.jsp" in text or "登录" in text and "password" in text


def _json(response: requests.Response) -> Any:
    try:
        return response.json()
    except (ValueError, json.JSONDecodeError) as error:
        raise PortalContractError("CAAC 接口未返回有效 JSON") from error


class PortalClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_lock = RLock()
        self.keepalive = SessionKeepAlive(keepalive_interval_factory, timeout, "caac-pilot-cookie-keepalive")
        self.cookies: dict[str, str] = {}
        self.copyable_credentials = ""
        self.verified_at = ""
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
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
                response = self.session.post(
                    self._url(path),
                    params={"ajaxPrefilter": str(int(time.time() * 1000))},
                    data=data,
                    headers={"Referer": self._url("/yzzzm/rygl/pilotredirect"), "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                    timeout=self.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise PortalError(f"CAAC 请求失败：{error.__class__.__name__}") from error
        if response.status_code in {301, 302, 303, 307, 308} or _is_login_response(response):
            raise PortalSessionExpired("CAAC 登录凭据已失效，请重新复制已登录请求")
        if response.status_code != 200:
            raise PortalError(f"CAAC HTTP 请求失败（状态 {response.status_code}）")
        return response

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain="fsop.caac.gov.cn", path="/")
        try:
            payload = _json(self._post(LIST_PATH, self._list_form(1, 1)))
            rows, total = self._parse_page(payload)
            if total < 0 or not isinstance(rows, list):
                raise PortalContractError("CAAC 列表响应结构异常")
        except Exception:
            self.clear_credentials()
            raise
        self.cookies = cookies
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return {**credential_summary(cookies), "verifiedAt": self.verified_at, "total": total}

    @staticmethod
    def _list_form(page: int, rows: int = 10) -> dict[str, str]:
        return {"archiveNo": "", "idCode": "", "regionId": "", "nationality": "", "pilotname": "", "orgId": "", "licenseType": "", "medicalStatus": "", "copType": "", "page": str(page), "rows": str(rows), "sort": "archiveNo", "order": "asc"}

    @staticmethod
    def _parse_page(payload: Any) -> tuple[list[dict[str, Any]], int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise PortalContractError("CAAC 列表响应缺少 rows 数组")
        try:
            total = int(payload.get("total"))
        except (TypeError, ValueError) as error:
            raise PortalContractError("CAAC 列表响应缺少有效 total") from error
        rows = [row for row in payload["rows"] if isinstance(row, dict)]
        if len(rows) != len(payload["rows"]):
            raise PortalContractError("CAAC 列表 rows 包含非对象记录")
        return rows, total

    def check_session(self) -> None:
        self.require_credentials()
        payload = _json(self._post(LIST_PATH, self._list_form(1, 1)))
        self._parse_page(payload)

    def require_credentials(self) -> None:
        if not self.cookies:
            raise PortalSessionExpired("请先验证 CAAC 登录凭据")

    def fetch_page(self, page: int, page_size: int = 10) -> tuple[list[dict[str, Any]], int]:
        self.require_credentials()
        payload = _json(self._post(LIST_PATH, self._list_form(page, page_size)))
        return self._parse_page(payload)

    def fetch_all_pilots(self, page_size: int = 10) -> tuple[list[PilotRecord], int]:
        records: list[PilotRecord] = []
        seen: set[str] = set()
        total: int | None = None
        page = 1
        while True:
            rows, reported_total = self.fetch_page(page, page_size)
            total = reported_total if total is None else total
            if reported_total != total:
                raise PortalContractError("CAAC 分页 total 在批次内发生变化")
            if not rows and len(records) < total:
                raise PortalContractError("CAAC 分页提前返回空页")
            new_count = 0
            for row in rows:
                pilot_id = str(row.get("pilotId") or "").strip()
                if not pilot_id:
                    raise PortalContractError("CAAC 列表记录缺少 pilotId")
                if pilot_id in seen:
                    raise PortalContractError("CAAC 分页返回重复 pilotId")
                seen.add(pilot_id)
                records.append(PilotRecord(len(records), row))
                new_count += 1
            if len(records) >= total:
                break
            if new_count == 0:
                raise PortalContractError("CAAC 分页没有前进")
            page += 1
        return records, int(total)

    def fetch_detail(self, pilot_id: str) -> dict[str, Any]:
        self.require_credentials()
        response = self._post(DETAIL_PATH, {"pilotId": str(pilot_id)})
        payload = _json(response)
        if not isinstance(payload, dict) or str(payload.get("pilotId") or "") != str(pilot_id):
            raise PortalContractError("CAAC 详情无法按 pilotId 归属")
        return payload

    def query_one(self, record: PilotRecord) -> PilotOutcome:
        detail = self.fetch_detail(record.pilot_id)
        return PilotOutcome(record, "成功", detail=detail)

    def invalidate_credentials(self) -> None:
        self.clear_credentials()

    def clear_credentials(self) -> None:
        self.cookies = {}
        self.copyable_credentials = ""
        self.verified_at = ""
        self.session.cookies.clear()

    def close(self) -> None:
        self.keepalive.stop()
        self.session.close()
