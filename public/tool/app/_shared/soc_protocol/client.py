from __future__ import annotations

from threading import RLock
from typing import Callable
from urllib.parse import urljoin

import requests

from .contract import (
    BASE_URL,
    FLIGHTS_PATH,
    NAVIGATION_PATH,
    PAGE_PATH,
    REASONS_PATH,
    STAFF_MOBILE_PATH,
    STAFF_VALIDATE_PATH,
    SUBMIT_PATH,
    SUGGEST_PATH,
    SocProtocolError,
    SocSessionExpired,
    is_login_response,
    parse_current_identity,
    parse_flight_options,
    parse_json,
    parse_staff_identity,
    parse_staff_mobile,
    parse_station_suggestions,
    parse_submit_outcome,
)
from .credentials import parse_credentials
from .models import FlightOption, StaffIdentity, SubmitOutcome


class SocProtocolClient:
    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        *,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
        timeout_seconds: int = 30,
    ) -> None:
        self.session = session or session_factory()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.request_lock = RLock()
        self.cookies: dict[str, str] = {}
        self.identity: dict[str, str] | None = None

    def url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def headers(self, referer: str = PAGE_PATH) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.base_url,
            "Referer": self.url(referer),
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0",
        }

    def request(self, method: str, path: str, *, data: object | None = None, action: str = "SOC 请求") -> object:
        with self.request_lock:
            try:
                response = self.session.request(
                    method.upper(),
                    self.url(path),
                    headers=self.headers(),
                    data=data if method.upper() == "POST" else None,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise SocProtocolError(f"{action}连接失败：{error.__class__.__name__}") from error
        if is_login_response(response):
            self.clear_credentials()
            raise SocSessionExpired("SOC 登录凭据已失效，请重新复制凭据")
        status = int(getattr(response, "status_code", 0) or 0)
        if status != 200:
            raise SocProtocolError(f"{action}返回 HTTP {status}")
        return response

    def load_credentials(self, source: str) -> tuple[dict[str, str], dict[str, str] | None]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        self.session.cookies.update(cookies)
        try:
            response = self.request("GET", PAGE_PATH, action="验证 SOC 凭据")
            html = str(getattr(response, "text", "") or "")
            if "applyFm" not in html or "KkTvlApply" not in html:
                raise SocSessionExpired("凭据未进入 SOC 随机置位页面")
            identity_response = self.request("GET", NAVIGATION_PATH, action="读取 SOC 当前登录人")
            self.identity = parse_current_identity(
                str(getattr(identity_response, "text", "") or ""),
                int(getattr(identity_response, "status_code", 0) or 0),
            )
        except Exception:
            self.clear_credentials()
            raise
        self.cookies = cookies
        return cookies, self.identity

    def check_session(self) -> None:
        if not self.cookies:
            raise SocSessionExpired("尚未验证 SOC 凭据")
        response = self.request("GET", PAGE_PATH, action="检查 SOC 会话")
        html = str(getattr(response, "text", "") or "")
        if "applyFm" not in html or "KkTvlApply" not in html:
            self.clear_credentials()
            raise SocSessionExpired("SOC 会话未进入随机置位页面")

    def station_suggestions(self, pinyin: str) -> tuple[object, list[str]]:
        response = self.request("POST", SUGGEST_PATH, data={"dataJson": pinyin}, action="查询 SOC 站点建议")
        return response, parse_station_suggestions(parse_json(response, "SOC 站点建议"))

    def apply_reasons(self) -> tuple[object, object]:
        response = self.request("POST", REASONS_PATH, data=[], action="核对 SOC 申请原因")
        return response, parse_json(response, "SOC 申请原因")

    def flight_options(self, flight_date: str, departure: str, arrival: str) -> tuple[object, list[FlightOption]]:
        response = self.request("POST", FLIGHTS_PATH, data={
            "kkTvlApplyVO.fltDt": flight_date,
            "kkTvlApplyVO.depArpCd": departure,
            "kkTvlApplyVO.arvArpCd": arrival,
        }, action="查询 SOC 动态航班")
        return response, parse_flight_options(parse_json(response, "SOC 动态航班"))

    def validate_staff(self, form: dict[str, str]) -> tuple[object, StaffIdentity]:
        response = self.request("POST", STAFF_VALIDATE_PATH, data=form, action="校验 SOC 员工")
        identity = parse_staff_identity(parse_json(response, "SOC 员工校验"), form["staffNums"])
        return response, identity

    def staff_mobile(self, employee_id: str) -> tuple[object, str]:
        response = self.request(
            "POST", STAFF_MOBILE_PATH, data={"staffNum": employee_id}, action="查询 SOC 员工手机号",
        )
        return response, parse_staff_mobile(parse_json(response, "SOC 员工手机号"))

    def submit(self, form: dict[str, str]) -> tuple[object, SubmitOutcome]:
        response = self.request("POST", SUBMIT_PATH, data=form, action="提交 SOC 随机置位")
        return response, parse_submit_outcome(parse_json(response, "SOC 随机置位提交"))

    def raw_json(self, path: str, form: list[tuple[str, str]], action: str) -> tuple[object, object]:
        response = self.request("POST", path, data=form, action=action)
        return response, parse_json(response, action)

    def clear_credentials(self) -> None:
        self.cookies = {}
        self.identity = None
        try:
            self.session.cookies.clear()
        except AttributeError:
            pass

    def close(self) -> None:
        self.clear_credentials()
        close = getattr(self.session, "close", None)
        if callable(close):
            close()
