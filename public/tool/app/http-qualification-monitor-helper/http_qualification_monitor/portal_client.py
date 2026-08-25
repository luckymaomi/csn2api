from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from threading import RLock
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .credentials import REQUIRED_COOKIE_NAMES, credential_summary, format_credentials, parse_credentials
from .models import QualificationGroup, QualificationItem
from .session_keepalive import SessionKeepAlive, random_keepalive_interval


BASE_URL = "https://ieb.csair.com"
HOME_PATH = "/index/index"
CLASSIFICATION_PATH = "/newieb/qualification/alarm/new/queryQualificationTypeParent"
EXPORT_PATH = "/newieb/qualification/alarm/new/exportQualificationInfoExcel"
EXPECTED_GROUPS = {
    "ZZYX": "资质运行类",
    "ZZZG": "资质资格类",
    "ZZTS": "资质特殊类",
}
EMPTY_FILTERS = (
    "staffNum",
    "alarmType",
    "primaryBase",
    "manyStaffNum",
    "manyAlarmType",
    "base",
    "fleetCd",
    "allClear",
    "effective",
    "effectiveModel",
)
OOXML_REQUIRED_PARTS = {"[Content_Types].xml", "xl/workbook.xml"}


class PortalError(RuntimeError):
    pass


class PortalSessionExpired(PortalError):
    pass


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_current_identity(html: str, status_code: int) -> dict[str, str]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    name_node = soup.select_one("#personalInfo .name-txt")
    staff_node = soup.select_one(".detailInfo .empid span[title]")
    name = _clean_text(name_node.get_text(" ", strip=True)) if name_node else ""
    staff_number = _clean_text(staff_node.get("title")) if staff_node else ""
    if status_code != 200 or not re.fullmatch(r"\d{6}", staff_number) or not name:
        raise ValueError("飞行门户首页没有返回可识别的当前登录人")
    return {"staffNumber": staff_number, "name": name}


def _is_login_response(response: object) -> bool:
    path = urlparse(str(getattr(response, "url", "") or "")).path.lower()
    if path == "/login" or path.endswith("/login"):
        return True
    content = bytes(getattr(response, "content", b"") or b"")[:8192].lower()
    text = str(getattr(response, "text", "") or "")[:8192].lower()
    sample = text + content.decode("utf-8", errors="ignore")
    return "scanlogin" in sample or "name=\"password\"" in sample or "name='password'" in sample


def parse_classification_tree(payload: object) -> list[QualificationGroup]:
    if not isinstance(payload, list):
        raise PortalError("资质分类接口未返回 JSON 数组")
    groups: list[QualificationGroup] = []
    group_codes: set[str] = set()
    item_codes: set[str] = set()
    for raw_group in payload:
        if not isinstance(raw_group, dict):
            raise PortalError("资质分类父项结构异常")
        code = _clean_text(raw_group.get("msgCode"))
        name = _clean_text(raw_group.get("msgType"))
        children = raw_group.get("sonList")
        if code not in EXPECTED_GROUPS or code in group_codes:
            raise PortalError(f"资质分类父项异常：{code or '缺少代码'}")
        if name != EXPECTED_GROUPS[code] or not isinstance(children, list) or not children:
            raise PortalError(f"资质分类父项契约异常：{code}")
        items: list[QualificationItem] = []
        for raw_item in children:
            if not isinstance(raw_item, dict):
                raise PortalError(f"资质分类子项结构异常：{code}")
            item_code = _clean_text(raw_item.get("msgCode"))
            item_name = _clean_text(raw_item.get("msgType"))
            if not item_code or not item_name or item_code in item_codes:
                raise PortalError(f"资质分类子项缺失或重复：{item_code or '缺少代码'}")
            item_codes.add(item_code)
            items.append(QualificationItem(item_name, item_code))
        group_codes.add(code)
        groups.append(QualificationGroup(name, code, items))
    if group_codes != set(EXPECTED_GROUPS):
        missing = ", ".join(code for code in EXPECTED_GROUPS if code not in group_codes)
        raise PortalError(f"资质分类缺少父项：{missing}")
    return groups


def build_export_params(qualification_code: str) -> dict[str, str]:
    code = _clean_text(qualification_code)
    if not code:
        raise ValueError("资质代码不能为空")
    return {"qualType": code, **{name: "" for name in EMPTY_FILTERS}}


def validate_ooxml(content: bytes) -> bytes:
    if not isinstance(content, bytes) or not content.startswith(b"PK"):
        raise PortalError("门户导出未返回 OOXML 文件")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if not OOXML_REQUIRED_PARTS.issubset(names):
                raise PortalError("门户导出缺少 OOXML 必要部件")
            if not any(name.startswith("xl/worksheets/") and name.endswith(".xml") for name in names):
                raise PortalError("门户导出缺少 worksheet")
            for name in OOXML_REQUIRED_PARTS:
                archive.read(name)
    except PortalError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise PortalError("门户导出不是有效 OOXML 文件") from error
    return content


class PortalClient:
    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 60,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_lock = RLock()
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-qualification-monitor-cookie-keepalive",
        )
        self.verified = False
        self.identity: dict[str, str] | None = None
        self.copyable_credentials = ""
        self.verified_at = ""
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": f"{self.base_url}/index/index",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _get(
        self,
        path: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> object:
        with self.request_lock:
            try:
                response = self.session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except requests.RequestException as error:
                raise PortalError(f"无法连接飞行门户：{error.__class__.__name__}") from error
            except Exception as error:
                status = getattr(locals().get("response"), "status_code", "未知")
                raise PortalError(f"飞行门户 HTTP 请求失败（状态 {status}）") from error
            if _is_login_response(response):
                self.invalidate_credentials()
                raise PortalSessionExpired("登录凭据已失效，请重新复制已登录请求")
            return response

    def load_credentials(self, source: str) -> tuple[dict[str, object], list[QualificationGroup]]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        with self.request_lock:
            for name in REQUIRED_COOKIE_NAMES:
                self.session.cookies.set(name, cookies[name], domain="ieb.csair.com", path="/")
        try:
            response = self._get(CLASSIFICATION_PATH, {})
            try:
                payload = response.json()  # type: ignore[attr-defined]
            except (ValueError, json.JSONDecodeError) as error:
                raise PortalSessionExpired("资质分类接口未返回有效 JSON，请重新验证凭据") from error
            groups = parse_classification_tree(payload)
            identity_response = self._get(HOME_PATH, {}, {"Accept": "text/html,application/xhtml+xml"})
            identity = parse_current_identity(
                str(getattr(identity_response, "text", "") or ""),
                int(getattr(identity_response, "status_code", 0) or 0),
            )
        except Exception:
            self.clear_credentials()
            raise
        self.verified = True
        self.identity = identity
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().isoformat(timespec="seconds")
        summary = {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "qualificationCount": sum(len(group.items) for group in groups),
            "identity": dict(identity),
        }
        return summary, groups

    def check_session(self) -> None:
        self.require_credentials()
        payload = self._get(CLASSIFICATION_PATH, {}).json()  # type: ignore[attr-defined]
        parse_classification_tree(payload)

    def require_credentials(self) -> None:
        if not self.verified:
            raise PortalSessionExpired("请先验证登录凭据")

    def export_qualification(self, qualification_code: str) -> bytes:
        self.require_credentials()
        response = self._get(EXPORT_PATH, build_export_params(qualification_code))
        return validate_ooxml(bytes(getattr(response, "content", b"") or b""))

    def invalidate_credentials(self) -> None:
        with self.request_lock:
            self.verified = False
            self.identity = None
            self.copyable_credentials = ""
            self.verified_at = ""
            self.session.cookies.clear()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.clear_credentials()
        self.session.close()
