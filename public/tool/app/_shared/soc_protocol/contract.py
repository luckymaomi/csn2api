from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .models import FlightOption, StaffIdentity, SubmitOutcome


BASE_URL = "https://soc.csair.com"
NAVIGATION_PATH = "/opws-web/pages/public/soc.jsp?f=2&s=11&t=1"
PAGE_PATH = "/opws-web/pages/aircrew/querypages/KkTvlApply-saveByKkTvlApplyData.jsp"
SUGGEST_PATH = "/opws-web/flightinfo-FlightPlan-findSuggest.action"
REASONS_PATH = "/opws-web/aircrew-KkTvlApply-getApplyReasons.action"
FLIGHTS_PATH = "/opws-web/aircrew-KkTvlApply-getFltNumList.action"
STAFF_VALIDATE_PATH = "/opws-web/aircrew-KkTvlApply-getStaffValidate.action"
STAFF_MOBILE_PATH = "/opws-web/aircrew-KkTvlApply-getStaffMobile.action"
SUBMIT_PATH = "/opws-web/aircrew-KkTvlApply-addKkTvlApply.action"

APPLY_REASONS: tuple[tuple[str, str], ...] = (
    ("26", "要客保障"), ("1", "商务跟机"), ("23", "保卫跟机"),
    ("29", "特殊装卸"), ("30", "军事信使"), ("28", "货机押运"),
    ("10", "本场训练"), ("5", "其它"), ("3", "复训"),
    ("4", "体检"), ("6", "学习培训"), ("8", "调配飞行"),
    ("9", "调勤帮飞"), ("15", "执行航班"), ("16", "航班调整"),
    ("2", "模拟机"), ("11", "飞行改装"), ("13", "航线检查"),
    ("25", "安全监察"), ("31", "外籍休假"),
)
APPLY_REASON_CODES = {label: code for code, label in APPLY_REASONS}
APPLY_REASON_LABELS = {code: label for code, label in APPLY_REASONS}

HOT_CITIES: tuple[str, ...] = (
    "广州", "北京首都", "北京大兴", "上海虹桥", "上海浦东", "贵阳",
    "长沙", "成都", "海口", "三亚", "重庆", "深圳", "杭州", "大连",
    "武汉", "沈阳", "桂林", "哈尔滨", "乌鲁木齐",
)


class SocProtocolError(RuntimeError):
    pass


class SocContractError(SocProtocolError):
    pass


class SocSessionExpired(SocProtocolError):
    pass


def is_login_response(response: object) -> bool:
    status = int(getattr(response, "status_code", 0) or 0)
    headers = getattr(response, "headers", {}) or {}
    location = str(headers.get("Location") or "")
    text = str(getattr(response, "text", "") or "")[:5000]
    redirected = status in {301, 302, 303, 307, 308} and "doSsoProxy" in location
    login_page = bool(re.search(r"(?i)iam|登录|login", text) and "KkTvlApply" not in text)
    return redirected or login_page


def parse_json(response: object, action: str) -> object:
    try:
        return response.json()  # type: ignore[attr-defined]
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise SocContractError(f"{action}响应不是有效 JSON") from error


def parse_current_identity(html: str, status_code: int = 200) -> dict[str, str] | None:
    if status_code != 200:
        return None
    soup = BeautifulSoup(str(html or ""), "html.parser")
    node = soup.select_one("#checkout_soc, #checkout")
    text = node.get_text(" ", strip=True) if isinstance(node, Tag) else ""
    match = re.search(r"欢迎您\s*[，,]\s*([^\s]+)", text)
    name = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    return {"name": name} if name else None


def parse_station_suggestions(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), list):
        raise SocContractError("SOC 站点建议响应缺少 result 数组")
    return [str(item).strip() for item in payload["result"] if str(item).strip()]


def parse_flight_options(payload: object) -> list[FlightOption]:
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise SocContractError("SOC 动态航班响应缺少 rows 数组")
    options: list[FlightOption] = []
    for raw in payload["rows"]:
        if not isinstance(raw, dict):
            raise SocContractError("SOC 动态航班 rows 包含非对象记录")
        values = [raw.get(key, "") for key in (
            "fltNr", "seqNr", "fltDt", "fltRoute", "fltTime", "crewDepDt", "subfleetType", "alnCd",
        )]
        airline = str(raw.get("alnCd") or "")
        number = str(raw.get("fltNr") or "")
        spare = str(raw.get("totalSpare") or "")
        subfleet = str(raw.get("subfleetType") or "")
        options.append(FlightOption(
            display_number=f"{airline}{number}{spare}{subfleet}",
            flight_number=number,
            sequence_number=str(raw.get("seqNr") or ""),
            flight_date=str(raw.get("fltDt") or ""),
            route=str(raw.get("fltRoute") or ""),
            flight_time=str(raw.get("fltTime") or ""),
            crew_departure=str(raw.get("crewDepDt") or ""),
            subfleet_type=subfleet,
            airline_code=airline,
            value=",".join(str(item or "") for item in values),
        ))
    return options


def _flight_digits(value: str) -> str:
    clean = re.sub(r"\([^)]*\)", "", value or "")
    match = re.search(r"(?<!\d)\d{1,4}(?!\d)", clean)
    return match.group(0) if match else ""


def flight_matches(option: FlightOption, requested: str) -> bool:
    wanted = _flight_digits(requested)
    return bool(wanted) and any(
        _flight_digits(candidate) == wanted
        for candidate in (option.flight_number, option.display_number, option.airline_code + option.flight_number)
    )


def choose_flight(options: list[FlightOption], requested: str) -> FlightOption:
    if not options:
        raise SocContractError("当前日期和航线没有可选择的航班")
    matches = [option for option in options if flight_matches(option, requested)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SocContractError(f"航班号匹配到多个动态航班 [{requested}]")
    if not requested and len(options) == 1:
        return options[0]
    available = ", ".join(option.display_number for option in options[:8])
    raise SocContractError(f"动态航班中没有匹配 [{requested}]，可选：{available}")


def build_staff_validation_form(
    employee_id: str,
    departure: str,
    arrival: str,
    flight_date: str,
    reason_code: str,
    route: str,
) -> dict[str, str]:
    return {
        "staffNums": employee_id,
        "depArpCd": departure,
        "arvArpCd": arrival,
        "fltDt": flight_date,
        "depArpCd2": "",
        "arvArpCd2": "",
        "fltDt2": flight_date,
        "applyReasonCd": reason_code,
        "hasSecondFlt": "N",
        "fltRoute": route,
    }


def parse_staff_identity(payload: object, expected_employee_id: str) -> StaffIdentity:
    if not isinstance(payload, dict):
        raise SocContractError("员工校验响应结构不是对象")
    feedback = str(payload.get("failFeedback") or "").strip()
    if feedback:
        raise SocProtocolError(feedback)
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise SocContractError("员工校验没有返回唯一可提交人员")
    row = rows[0]
    employee_id = str(row.get("staffNum") or expected_employee_id).strip()
    if employee_id != expected_employee_id:
        raise SocContractError("员工校验返回人员与请求员工号不一致")
    name = str(row.get("chnName") or "").strip()
    if not name:
        raise SocContractError("员工校验缺少中文名")
    return StaffIdentity(employee_id, name)


def parse_staff_mobile(payload: object) -> str:
    if not isinstance(payload, dict):
        raise SocContractError("员工手机号响应结构不是对象")
    return str(payload.get("staffMobile") or "").strip()


def build_submit_form(
    *,
    identity: StaffIdentity,
    flight_date: str,
    departure: str,
    arrival: str,
    option_value: str,
    reason_code: str,
    comment: str,
) -> dict[str, str]:
    return {
        "kkTvlStaffNum1": identity.employee_id,
        "kkTvlStaffMobile1": identity.mobile,
        "kkTvlPassportNum1": "",
        "kkTvlApplyVO.staffNum": identity.employee_id,
        "kkTvlApplyVO.staffMobile": identity.mobile,
        "kkTvlApplyVO.passportNum": "",
        "kkTvlApplyVO.fltDt": flight_date,
        "kkTvlApplyVO.depArpCd": departure,
        "kkTvlApplyVO.arvArpCd": arrival,
        "kkTvlApplyVO.fltNr": option_value,
        "kkTvlApplyVO.fltDt2": flight_date,
        "kkTvlApplyVO.depArpCd2": "",
        "kkTvlApplyVO.arvArpCd2": "",
        "kkTvlApplyVO.fltNr2": "",
        "kkTvlApplyVO.applyType": "KK",
        "kkTvlApplyVO.applyReasonCd": reason_code,
        "kkTvlApplyVO.seatSelection": "N",
        "kkTvlApplyVO.applyComment": comment,
    }


def parse_submit_outcome(payload: object) -> SubmitOutcome:
    if not isinstance(payload, dict):
        raise SocContractError("提交响应结构不是对象")
    message = str(payload.get("message") or "").strip()
    return SubmitOutcome(message == "录入成功！", message or "提交响应缺少业务消息")
