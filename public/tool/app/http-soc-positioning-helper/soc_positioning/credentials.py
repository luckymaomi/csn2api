"""Parse SOC Cookie/cURL text without executing the pasted command."""

from __future__ import annotations

import re


def _cookie_text(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        raise ValueError("请粘贴 SOC 登录凭据")
    for pattern in (
        r"(?is)(?:-b|--cookie)\s+['\"](.*?)['\"]",
        r"(?im)^\s*cookie\s*:\s*(.+?)\s*$",
        r"(?i)cookie\s*:\s*([^\r\n'\"]+)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    if "=" in text and "\n" not in text and "\r" not in text:
        return text.strip("'\"")
    raise ValueError("未在凭据中找到 SOC Cookie")


def parse_credentials(source: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in _cookie_text(source).split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name and value:
            parsed[name] = value.strip()
    if not parsed.get("JSESSIONID"):
        raise ValueError("SOC 凭据缺少 JSESSIONID")
    return parsed


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items() if value)
