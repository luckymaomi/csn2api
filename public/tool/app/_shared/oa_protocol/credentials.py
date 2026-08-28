from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from credential_text import normalize_credential_source


COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
MAX_USER_AGENT_LENGTH = 512


def _extract_cookie_text(source: str) -> str:
    text = normalize_credential_source(source).strip()
    if not text:
        raise ValueError("请粘贴 OA 登录凭据")
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
    labeled = re.match(r"(?is)^OA\s*[:：]\s*(.+)$", text)
    if labeled and "\n" not in text and "\r" not in text:
        return labeled.group(1).strip().strip("'\"")
    if "=" in text and "\n" not in text and "\r" not in text:
        return text.strip("'\"")
    raise ValueError("未在凭据中找到 Cookie Header")


def parse_credentials(source: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in _extract_cookie_text(source).split(";"):
        name, separator, value = part.strip().partition("=")
        name = name.strip()
        if separator and name and COOKIE_NAME_PATTERN.fullmatch(name):
            parsed[name] = value.strip()
    if not parsed or not any(parsed.values()):
        raise ValueError("Cookie Header 中没有有效 Cookie")
    return parsed


def _safe_user_agent(value: str) -> str:
    user_agent = value.strip().strip("'\"")
    return user_agent if user_agent and len(user_agent) <= MAX_USER_AGENT_LENGTH and "\r" not in user_agent and "\n" not in user_agent else ""


def parse_browser_headers(source: str) -> dict[str, str]:
    text = normalize_credential_source(source)
    for match in re.finditer(r"(?is)(?:-H|--header)\s+\^?(['\"])(.*?)\^?\1", text):
        name, separator, value = match.group(2).partition(":")
        if separator and name.strip().lower() == "user-agent":
            user_agent = _safe_user_agent(value)
            if user_agent:
                return {"User-Agent": user_agent}
    option = re.search(r"(?is)(?:-A|--user-agent)\s+\^?(['\"])(.*?)\^?\1", text)
    if option and (user_agent := _safe_user_agent(option.group(2))):
        return {"User-Agent": user_agent}
    header = re.search(r"(?im)^\s*user-agent\s*:\s*(.+?)\s*$", text)
    if header and (user_agent := _safe_user_agent(header.group(1))):
        return {"User-Agent": user_agent}
    return {}


def parse_waiting_template(source: str) -> dict[str, object] | None:
    text = normalize_credential_source(source)
    urls = re.findall(r"https://[^\s'\"]+", text, flags=re.IGNORECASE)
    if not any(urlsplit(url).hostname == "work.csair.com" and urlsplit(url).path == "/oai/work/box/query/waiting" for url in urls):
        return None
    match = re.search(r"(?is)(?:--data-raw|--data|-d)\s+\^?(['\"])(.*?)\^?\1", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    return {"cookieCount": len(cookies)}


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if value)
