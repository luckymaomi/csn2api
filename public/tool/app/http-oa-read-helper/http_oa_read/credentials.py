"""安全解析浏览器导出的 cURL 或 Cookie Header。"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit


COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
MAX_USER_AGENT_LENGTH = 512


def _extract_cookie_text(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        raise ValueError("请粘贴 OA 登录凭据")

    quoted_header = re.search(
        r"(?is)(?:-H|--header)\s+\^?(['\"])cookie\s*:\s*(.*?)\^?\1",
        text,
    )
    if quoted_header:
        return quoted_header.group(2).strip()

    quoted_cookie = re.search(r"(?is)(?:-b|--cookie)\s+\^?(['\"])(.*?)\^?\1", text)
    if quoted_cookie:
        return quoted_cookie.group(2).strip()

    header_line = re.search(r"(?im)^\s*cookie\s*:\s*(.+?)\s*$", text)
    if header_line:
        return header_line.group(1).strip().strip("'\"")

    inline_header = re.search(r"(?i)cookie\s*:\s*([^\r\n'\"]+)", text)
    if inline_header:
        return inline_header.group(1).strip()

    if "=" in text and "\n" not in text and "\r" not in text:
        return text.strip("'\"")
    raise ValueError("未在凭据中找到 Cookie Header")


def parse_credentials(source: str) -> dict[str, str]:
    cookie_text = _extract_cookie_text(source)
    parsed: dict[str, str] = {}
    for part in cookie_text.split(";"):
        name, separator, value = part.strip().partition("=")
        name = name.strip()
        if not separator or not name or not COOKIE_NAME_PATTERN.fullmatch(name):
            continue
        parsed[name] = value.strip()
    if not parsed or not any(value for value in parsed.values()):
        raise ValueError("Cookie Header 中没有有效 Cookie")
    return parsed


def _safe_user_agent(value: str) -> str:
    user_agent = value.strip().strip("'\"")
    if not user_agent or len(user_agent) > MAX_USER_AGENT_LENGTH:
        return ""
    if "\r" in user_agent or "\n" in user_agent:
        return ""
    return user_agent


def parse_browser_headers(source: str) -> dict[str, str]:
    """只从 cURL/请求头文本中复用浏览器 User-Agent。"""
    text = str(source or "")
    for match in re.finditer(r"(?is)(?:-H|--header)\s+\^?(['\"])(.*?)\^?\1", text):
        name, separator, value = match.group(2).partition(":")
        if separator and name.strip().lower() == "user-agent":
            user_agent = _safe_user_agent(value)
            if user_agent:
                return {"User-Agent": user_agent}

    option = re.search(r"(?is)(?:-A|--user-agent)\s+\^?(['\"])(.*?)\^?\1", text)
    if option:
        user_agent = _safe_user_agent(option.group(2))
        if user_agent:
            return {"User-Agent": user_agent}

    header_line = re.search(r"(?im)^\s*user-agent\s*:\s*(.+?)\s*$", text)
    if header_line:
        user_agent = _safe_user_agent(header_line.group(1))
        if user_agent:
            return {"User-Agent": user_agent}
    return {}


def parse_waiting_payload(source: str) -> dict[str, object] | None:
    """从 waiting 的完整 cURL 中提取 JSON 请求模板，不执行命令。"""
    text = str(source or "")
    urls = re.findall(r"https://[^\s'\"]+", text, flags=re.IGNORECASE)
    if not any(
        urlsplit(url).hostname == "work.csair.com"
        and urlsplit(url).path == "/oai/work/box/query/waiting"
        for url in urls
    ):
        return None

    body_match = re.search(
        r"(?is)(?:--data-raw|--data|-d)\s+\^?(['\"])(.*?)\^?\1",
        text,
    )
    if not body_match:
        return None
    try:
        payload = json.loads(body_match.group(2))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    return {"cookieCount": len(cookies)}


def format_all_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if value)
