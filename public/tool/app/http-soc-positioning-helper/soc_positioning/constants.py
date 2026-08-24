"""SOC positioning constants confirmed from the current page."""

from __future__ import annotations


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

BASE_URL = "https://soc.csair.com"
PAGE_PATH = "/opws-web/pages/aircrew/querypages/KkTvlApply-saveByKkTvlApplyData.jsp"
SUGGEST_PATH = "/opws-web/flightinfo-FlightPlan-findSuggest.action"
REASONS_PATH = "/opws-web/aircrew-KkTvlApply-getApplyReasons.action"
FLIGHTS_PATH = "/opws-web/aircrew-KkTvlApply-getFltNumList.action"
STAFF_VALIDATE_PATH = "/opws-web/aircrew-KkTvlApply-getStaffValidate.action"
STAFF_MOBILE_PATH = "/opws-web/aircrew-KkTvlApply-getStaffMobile.action"
SUBMIT_PATH = "/opws-web/aircrew-KkTvlApply-addKkTvlApply.action"
