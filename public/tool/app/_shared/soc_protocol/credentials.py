from __future__ import annotations

import re

from credential_text import normalize_credential_source


COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _extract_cookie_text(source: str) -> str:
    text = normalize_credential_source(source).strip()
    if not text:
        raise ValueError("请粘贴 SOC 登录凭据")
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
    raise ValueError("未在凭据中找到 SOC Cookie")


def parse_credentials(source: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in _extract_cookie_text(source).split(";"):
        name, separator, value = part.strip().partition("=")
        name = name.strip()
        if separator and name and COOKIE_NAME_PATTERN.fullmatch(name) and value.strip():
            parsed[name] = value.strip()
    if not parsed.get("JSESSIONID"):
        raise ValueError("SOC 凭据缺少 JSESSIONID")
    return parsed


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items() if value)


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    names = [name for name, value in cookies.items() if value]
    return {"ready": bool(names), "cookieNames": names, "cookieCount": len(names)}
