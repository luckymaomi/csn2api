"""HTTP client for the SOC random positioning application."""

from __future__ import annotations

import random
import re
import threading
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup
from typing import Callable

from .constants import (
    BASE_URL, FLIGHTS_PATH, PAGE_PATH, STAFF_MOBILE_PATH, STAFF_VALIDATE_PATH,
    SUBMIT_PATH, SUGGEST_PATH,
)
from .credentials import format_credentials, parse_credentials
from .models import FlightOption, StaffIdentity, SubmitOutcome
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


class PortalError(RuntimeError):
    pass


class PortalSessionExpired(PortalError):
    pass


def _random_value() -> str:
    return str(random.randint(1000000000, 9999999999))


def _login_like(response: requests.Response) -> bool:
    location = response.headers.get("Location", "")
    text = response.text or ""
    return response.status_code in {301, 302, 303, 307, 308} and "doSsoProxy" in location or bool(
        re.search(r"(?i)iam|登录|login", text[:5000]) and "KkTvlApply" not in text
    )


class SocPortalClient:
    def __init__(
        self,
        timeout: int = 30,
        session: requests.Session | None = None,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()
        self.request_lock = threading.RLock()
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-soc-positioning-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""
        self.verified = False

    def _headers(self, referer: str = PAGE_PATH) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}{referer}",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0",
        }

    def _check(self, response: requests.Response) -> requests.Response:
        if _login_like(response):
            self.verified = False
            raise PortalSessionExpired("SOC 登录凭据已失效，请重新复制凭据")
        try:
            response.raise_for_status()
        except requests.RequestException as error:
            raise PortalError(f"SOC HTTP 请求失败（状态 {response.status_code}）") from error
        return response

    def _get(self, path: str) -> requests.Response:
        with self.request_lock:
            try:
                response = self.session.get(BASE_URL + path, headers=self._headers(), timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as error:
                raise PortalError(f"无法连接 SOC：{error.__class__.__name__}") from error
        return self._check(response)

    def _post(self, path: str, data: Any) -> requests.Response:
        with self.request_lock:
            try:
                response = self.session.post(BASE_URL + path, headers=self._headers(), data=data, timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as error:
                raise PortalError(f"SOC 请求失败：{error.__class__.__name__}") from error
        return self._check(response)

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        with self.request_lock:
            self.session.cookies.update(cookies)
        response = self._get(PAGE_PATH)
        html = response.text or ""
        if "applyFm" not in html or "KkTvlApply" not in html:
            raise PortalSessionExpired("凭据未进入 SOC 随机置位页面")
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.verified = True
        return {"verifiedAt": self.verified_at, "cookieCount": len(cookies)}

    def check_session(self) -> None:
        if not self.verified:
            raise PortalSessionExpired("尚未验证 SOC 凭据")
        response = self._get(PAGE_PATH)
        if "applyFm" not in (response.text or "") or "KkTvlApply" not in (response.text or ""):
            raise PortalSessionExpired("SOC 会话未进入随机置位页面")

    def invalidate_credentials(self) -> None:
        with self.request_lock:
            self.session.cookies.clear()
            self.copyable_credentials = ""
            self.verified_at = ""
            self.verified = False

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        with self.request_lock:
            self.invalidate_credentials()

    def close(self) -> None:
        self.clear_credentials()
        close = getattr(self.session, "close", None)
        if callable(close):
            close()

    def suggest(self, pinyin: str) -> list[str]:
        response = self._post(SUGGEST_PATH, {"dataJson": pinyin})
        try:
            payload = response.json()
            return [str(item) for item in payload.get("result", [])] if isinstance(payload, dict) else []
        except (ValueError, TypeError) as error:
            raise PortalError("SOC 站点建议响应不是有效 JSON") from error

    @staticmethod
    def _option(row: dict[str, Any]) -> FlightOption:
        values = [row.get(key, "") for key in ("fltNr", "seqNr", "fltDt", "fltRoute", "fltTime", "crewDepDt", "subfleetType", "alnCd")]
        value = ",".join(str(item or "") for item in values)
        aln = str(row.get("alnCd", "") or "")
        number = str(row.get("fltNr", "") or "")
        spare = str(row.get("totalSpare", "") or "")
        subfleet = str(row.get("subfleetType", "") or "")
        return FlightOption(
            display_number=f"{aln}{number}{spare}{subfleet}", flight_number=number,
            sequence_number=str(row.get("seqNr", "") or ""), flight_date=str(row.get("fltDt", "") or ""),
            route=str(row.get("fltRoute", "") or ""), flight_time=str(row.get("fltTime", "") or ""),
            crew_departure=str(row.get("crewDepDt", "") or ""), subfleet_type=subfleet,
            airline_code=aln, value=value,
        )

    def list_flights(self, flight_date: str, departure: str, arrival: str) -> list[FlightOption]:
        response = self._post(FLIGHTS_PATH, {
            "kkTvlApplyVO.fltDt": flight_date,
            "kkTvlApplyVO.depArpCd": departure,
            "kkTvlApplyVO.arvArpCd": arrival,
        })
        try:
            payload = response.json()
            rows = payload.get("rows", []) if isinstance(payload, dict) else []
            return [self._option(row) for row in rows if isinstance(row, dict)]
        except (ValueError, TypeError) as error:
            raise PortalError("SOC 动态航班响应不是有效 JSON") from error

    @staticmethod
    def _flight_match(option: FlightOption, requested: str) -> bool:
        def flight_digits(value: str) -> str:
            # 航班下拉项可能附带计划时刻；航班号数字本身是业务唯一键。
            clean = re.sub(r"\([^)]*\)", "", value or "")
            match = re.search(r"(?<!\d)\d{1,4}(?!\d)", clean)
            return match.group(0) if match else ""

        wanted = flight_digits(requested)
        if not wanted:
            return False
        return any(flight_digits(candidate) == wanted for candidate in (
            option.flight_number,
            option.display_number,
            option.airline_code + option.flight_number,
        ))

    def choose_flight(self, options: list[FlightOption], requested: str) -> FlightOption:
        if not options:
            raise PortalError("当前日期和航线没有可选择的航班")
        matches = [option for option in options if self._flight_match(option, requested)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise PortalError(f"航班号匹配到多个动态航班 [{requested}]")
        if not requested and len(options) == 1:
            return options[0]
        available = ", ".join(option.display_number for option in options[:8])
        raise PortalError(f"动态航班中没有匹配 [{requested}]，可选：{available}")

    def validate_staff(self, record: dict[str, object], option: FlightOption) -> StaffIdentity:
        response = self._post(STAFF_VALIDATE_PATH, {
            "staffNums": str(record["员工号"]), "depArpCd": str(record["出发地"]),
            "arvArpCd": str(record["目的地"]), "fltDt": str(record["航班日期"]),
            "depArpCd2": "", "arvArpCd2": "", "fltDt2": str(record["航班日期"]),
            "applyReasonCd": str(record["申请原因代码"]), "hasSecondFlt": "N", "fltRoute": option.route,
        })
        try:
            payload = response.json()
        except ValueError as error:
            raise PortalError("员工校验响应不是有效 JSON") from error
        feedback = str(payload.get("failFeedback", "") or "") if isinstance(payload, dict) else ""
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        if feedback:
            raise PortalError(feedback)
        if not rows or not isinstance(rows[0], dict):
            raise PortalError("员工校验没有返回可提交人员")
        row = rows[0]
        employee_id = str(row.get("staffNum", record["员工号"]) or record["员工号"])
        name = str(row.get("chnName", "") or "")
        if not name:
            raise PortalError("员工校验缺少中文名")
        mobile_response = self._post(STAFF_MOBILE_PATH, {"staffNum": employee_id})
        try:
            mobile_payload = mobile_response.json()
        except ValueError as error:
            raise PortalError("员工手机号响应不是有效 JSON") from error
        mobile = str(mobile_payload.get("staffMobile", "") or "") if isinstance(mobile_payload, dict) else ""
        return StaffIdentity(employee_id, name, mobile)

    def submit(self, record: dict[str, object], option: FlightOption, identity: StaffIdentity) -> SubmitOutcome:
        data = {
            "kkTvlStaffNum1": identity.employee_id, "kkTvlStaffMobile1": identity.mobile, "kkTvlPassportNum1": "",
            "kkTvlApplyVO.staffNum": identity.employee_id, "kkTvlApplyVO.staffMobile": identity.mobile,
            "kkTvlApplyVO.passportNum": "", "kkTvlApplyVO.fltDt": str(record["航班日期"]),
            "kkTvlApplyVO.depArpCd": str(record["出发地"]), "kkTvlApplyVO.arvArpCd": str(record["目的地"]),
            "kkTvlApplyVO.fltNr": option.value, "kkTvlApplyVO.fltDt2": str(record["航班日期"]),
            "kkTvlApplyVO.depArpCd2": "", "kkTvlApplyVO.arvArpCd2": "", "kkTvlApplyVO.fltNr2": "",
            "kkTvlApplyVO.applyType": "KK", "kkTvlApplyVO.applyReasonCd": str(record["申请原因代码"]),
            "kkTvlApplyVO.seatSelection": "N", "kkTvlApplyVO.applyComment": str(record.get("备注", "") or ""),
        }
        response = self._post(SUBMIT_PATH, data)
        try:
            payload = response.json()
        except ValueError as error:
            raise PortalError("提交响应不是有效 JSON") from error
        message = str(payload.get("message", "") or "") if isinstance(payload, dict) else ""
        return SubmitOutcome(message == "录入成功！", message or "提交响应缺少业务消息")
