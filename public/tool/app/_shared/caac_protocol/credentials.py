from __future__ import annotations

import re


REQUIRED_COOKIE_NAMES = ("yzzzm", "JSESSIONID", "home")


def _extract_cookie_text(source: str) -> str:
    text = str(source or "").strip()
    if not text:
        raise ValueError("请粘贴 CAAC 已登录请求的 cURL 或 Cookie Header")
    for pattern in (
        r"(?is)(?:-H|--header)\s+['\"]cookie\s*:\s*(.*?)['\"]",
        r"(?is)(?:-b|--cookie)\s+\$?['\"](.*?)['\"]",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    line = re.search(r"(?im)^\s*cookie\s*:\s*(.+?)\s*$", text)
    if line:
        return line.group(1).strip().strip("'\"")
    if "=" in text and "\n" not in text and "\r" not in text:
        return text.strip("'\"")
    raise ValueError("未在输入中找到 Cookie Header")


def _decode_shell_cookie(value: str) -> str:
    def replace_unicode(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return re.sub(r"\\u([0-9a-fA-F]{4})", replace_unicode, str(value or "")).replace("\\_", "_")


def parse_credentials(source: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in _decode_shell_cookie(_extract_cookie_text(source)).split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name in REQUIRED_COOKIE_NAMES and value.strip():
            parsed[name] = value.strip()
    missing = [name for name in REQUIRED_COOKIE_NAMES if not parsed.get(name)]
    if missing:
        raise ValueError(f"登录凭据缺少 Cookie：{', '.join(missing)}")
    return parsed


def format_credentials(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={cookies[name]}" for name in REQUIRED_COOKIE_NAMES if cookies.get(name))


def credential_summary(cookies: dict[str, str]) -> dict[str, object]:
    names = [name for name in REQUIRED_COOKIE_NAMES if cookies.get(name)]
    return {"cookieNames": names, "cookieCount": len(names)}
