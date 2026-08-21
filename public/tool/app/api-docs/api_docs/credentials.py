from __future__ import annotations

import json
import re
from urllib.parse import urlsplit


REQUIRED_COOKIE_NAMES = ("JSESSIONID", "iebJSid")
COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
MAX_USER_AGENT_LENGTH = 512


def _extract_cookie_text(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        raise ValueError("请粘贴 Cookie Header 或 Copy as cURL")

    quoted_header = re.search(
        r"(?is)(?:-H|--header)\s+\^?(['\"])cookie\s*:\s*(.*?)\^?\1",
        text,
    )
    if quoted_header:
        return quoted_header.group(2).strip()

    quoted_cookie = re.search(
        r"(?is)(?:-b|--cookie)\s+\^?(['\"])(.*?)\^?\1",
        text,
    )
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
    raise ValueError("未在输入中找到 Cookie Header")


def parse_credentials(source: str) -> dict[str, str]:
    cookie_text = _extract_cookie_text(source)
    cookies: dict[str, str] = {}
    for part in cookie_text.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name in REQUIRED_COOKIE_NAMES:
            cookies[name] = value.strip()
    missing = [name for name in REQUIRED_COOKIE_NAMES if not cookies.get(name)]
    if missing:
        raise ValueError(f"登录凭据缺少 Cookie：{', '.join(missing)}")
    return cookies


def parse_all_credentials(source: str) -> dict[str, str]:
    cookie_text = _extract_cookie_text(source)
    cookies: dict[str, str] = {}
    for part in cookie_text.split(";"):
        name, separator, value = part.strip().partition("=")
        name = name.strip()
        if separator and name and COOKIE_NAME_PATTERN.fullmatch(name):
            cookies[name] = value.strip()
    if not cookies or not any(cookies.values()):
        raise ValueError("Cookie Header 中没有有效 Cookie")
    return cookies


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(
        f"{name}={cookies[name]}"
        for name in REQUIRED_COOKIE_NAMES
        if cookies.get(name)
    )


def format_all_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if value)


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    names = [name for name in REQUIRED_COOKIE_NAMES if cookies.get(name)]
    return {"ready": len(names) == len(REQUIRED_COOKIE_NAMES), "cookieNames": names, "cookieCount": len(names)}


def all_credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    names = [name for name, value in cookies.items() if value]
    return {"ready": bool(names), "cookieNames": names, "cookieCount": len(names)}


def parse_browser_user_agent(source: str) -> str:
    text = str(source or "")
    candidates: list[str] = []
    for match in re.finditer(r"(?is)(?:-H|--header)\s+\^?(['\"])(.*?)\^?\1", text):
        name, separator, value = match.group(2).partition(":")
        if separator and name.strip().lower() == "user-agent":
            candidates.append(value)
    option = re.search(r"(?is)(?:-A|--user-agent)\s+\^?(['\"])(.*?)\^?\1", text)
    if option:
        candidates.append(option.group(2))
    header_line = re.search(r"(?im)^\s*user-agent\s*:\s*(.+?)\s*$", text)
    if header_line:
        candidates.append(header_line.group(1))
    for candidate in candidates:
        value = candidate.strip().strip("'\"")
        if value and len(value) <= MAX_USER_AGENT_LENGTH and "\r" not in value and "\n" not in value:
            return value
    return ""


def parse_waiting_template(source: str) -> dict[str, object] | None:
    text = str(source or "")
    urls = re.findall(r"https://[^\s'\"]+", text, flags=re.IGNORECASE)
    if not any(
        urlsplit(url).hostname == "work.csair.com"
        and urlsplit(url).path == "/oai/work/box/query/waiting"
        for url in urls
    ):
        return None
    body_match = re.search(r"(?is)(?:--data-raw|--data|-d)\s+\^?(['\"])(.*?)\^?\1", text)
    if not body_match:
        return None
    try:
        payload = json.loads(body_match.group(2))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
