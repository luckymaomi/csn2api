from __future__ import annotations

import re
from threading import RLock
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ieb.csair.com"
HOME_PATH = "/index/index"
REQUIRED_COOKIE_NAMES = ("JSESSIONID", "iebJSid")


class IebProtocolError(RuntimeError):
    pass


class IebSessionExpired(IebProtocolError):
    pass


class IebContractError(IebProtocolError):
    pass


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _extract_cookie_text(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        raise ValueError("请粘贴登录凭据")
    labeled = re.match(r"(?is)^(?:飞行门户|IEB)\s*[:：]\s*(.+)$", text)
    if labeled and "\n" not in text and "\r" not in text:
        return labeled.group(1).strip().strip("'\"")
    for pattern in (
        r"(?is)(?:-H|--header)\s+\^?(['\"])cookie\s*:\s*(.*?)\^?\1",
        r"(?is)(?:-b|--cookie)\s+\^?(['\"])(.*?)\^?\1",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(2).strip()
    header = re.search(r"(?im)^\s*cookie\s*:\s*(.+?)\s*$", text)
    if header:
        return header.group(1).strip().strip("'\"")
    inline = re.search(r"(?i)cookie\s*:\s*([^\r\n'\"]+)", text)
    if inline:
        return inline.group(1).strip()
    if "=" in text and "\n" not in text and "\r" not in text:
        return text.strip("'\"")
    raise ValueError("未在凭据中找到 Cookie Header")


def parse_credentials(source: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in _extract_cookie_text(source).split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name in REQUIRED_COOKIE_NAMES and value.strip():
            parsed[name] = value.strip()
    missing = [name for name in REQUIRED_COOKIE_NAMES if not parsed.get(name)]
    if missing:
        raise ValueError(f"登录凭据缺少 Cookie：{', '.join(missing)}")
    return parsed


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(
        f"{name}={cookies[name]}" for name in REQUIRED_COOKIE_NAMES if cookies.get(name)
    )


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    names = [name for name in REQUIRED_COOKIE_NAMES if cookies.get(name)]
    return {"cookieNames": names, "cookieCount": len(names)}


def is_login_response(response: object) -> bool:
    path = urlparse(str(getattr(response, "url", "") or "")).path.lower()
    location = str(getattr(response, "headers", {}).get("Location", "") or "").lower()
    sample = str(getattr(response, "text", "") or "")[:8192].lower()
    return (
        path == "/login"
        or path.endswith("/login")
        or "/login" in location
        or "scanlogin" in sample
        or "name=\"password\"" in sample
        or "name='password'" in sample
    )


def parse_current_identity(html: str, status_code: int) -> dict[str, str]:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    name_node = soup.select_one("#personalInfo .name-txt")
    staff_node = soup.select_one(".detailInfo .empid span[title]")
    name = _text(name_node.get_text(" ", strip=True)) if name_node else ""
    staff_number = _text(staff_node.get("title")) if staff_node else ""
    if status_code != 200 or not re.fullmatch(r"\d{6}", staff_number) or not name:
        raise IebContractError("飞行门户首页没有返回可识别的当前登录人")
    return {"staffNumber": staff_number, "name": name}


class IebSession:
    """统一 IEB Cookie、请求锁、失效识别和当前登录人读取。"""

    def __init__(
        self,
        session: requests.Session | object | None = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_lock = RLock()
        self.cookies: dict[str, str] = {}
        self.identity: dict[str, str] | None = None
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{self.base_url}/index/index",
            "X-Requested-With": "XMLHttpRequest",
        })

    def url(self, path_or_url: str) -> str:
        if str(path_or_url).lower().startswith(("http://", "https://")):
            return str(path_or_url)
        return urljoin(self.base_url + "/", str(path_or_url).lstrip("/"))

    def load_credentials(self, source: str) -> dict[str, str]:
        cookies = parse_credentials(source)
        self.clear_credentials()
        for name in REQUIRED_COOKIE_NAMES:
            self.session.cookies.set(name, cookies[name], domain="ieb.csair.com", path="/")
        self.cookies = cookies
        return cookies

    def require_credentials(self) -> None:
        if not self.cookies:
            raise IebSessionExpired("请先验证飞行门户 Cookie")

    def request(self, method: str, path_or_url: str, **kwargs: Any) -> requests.Response:
        with self.request_lock:
            self.require_credentials()
            try:
                response = self.session.request(
                    method,
                    self.url(path_or_url),
                    timeout=self.timeout,
                    allow_redirects=True,
                    **kwargs,
                )
            except requests.RequestException as error:
                raise IebProtocolError(f"无法连接飞行门户：{error.__class__.__name__}") from error
            except Exception as error:
                if isinstance(error, IebProtocolError):
                    raise
                raise IebProtocolError("飞行门户 HTTP 请求失败") from error
            if is_login_response(response):
                self.clear_credentials()
                raise IebSessionExpired("飞行门户 Cookie 已失效，请重新复制")
            if int(getattr(response, "status_code", 0) or 0) != 200:
                raise IebProtocolError(f"飞行门户返回 HTTP {getattr(response, 'status_code', '未知')}")
            return response

    def fetch_identity(self) -> tuple[requests.Response, dict[str, str]]:
        response = self.request("GET", HOME_PATH, headers={"Accept": "text/html,application/xhtml+xml"})
        identity = parse_current_identity(str(response.text or ""), response.status_code)
        self.identity = identity
        return response, identity

    def clear_credentials(self) -> None:
        self.cookies = {}
        self.identity = None
        try:
            self.session.cookies.clear()
        except AttributeError:
            pass

    def close(self) -> None:
        self.clear_credentials()
        self.session.close()
