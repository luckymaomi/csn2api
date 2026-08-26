from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import IebContractError
from .lock_models import LockTypeMetadata, PortalMetadata


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_default_reason_prefix(html: str) -> str:
    match = re.search(
        r"(?is)lockReasonTxt[^\n;]*?\.val\((?P<expression>[^\n;]*?lockTypeDesc[^\n;]*?)\)",
        str(html or ""),
    )
    if not match:
        return ""
    expression = match.group("expression").split("lockTypeDesc", 1)[0]
    return "".join(fragment for _quote, fragment in re.findall(r"(['\"])(.*?)\1", expression))


def parse_portal_metadata(html: str) -> PortalMetadata:
    soup = BeautifulSoup(str(html or ""), "html.parser")
    select = soup.select_one("#showNonproductionTaskImportPage #lockType") or soup.select_one("#lockType")
    if select is None or soup.select_one("#nonproductionTaskImportForm") is None:
        raise IebContractError("录入页缺少有效表单或锁班类型列表")
    lock_types: dict[str, LockTypeMetadata] = {}
    for option in select.select("option[value]"):
        code = normalize_text(option.get("value"))
        if not code:
            continue
        if code in lock_types:
            raise IebContractError(f"录入页锁班类型代码重复：{code}")
        label = normalize_text(option.get_text(" ", strip=True))
        description = label.split("】", 1)[-1] if "】" in label else label
        class_value = option.get("class", [])
        lock_types[code] = LockTypeMetadata(
            code=code,
            label=label,
            description=description,
            limit_flag=normalize_text(" ".join(class_value) if isinstance(class_value, list) else class_value),
            date_split_flag=normalize_text(option.get("id")),
        )
    if not lock_types:
        raise IebContractError("录入页没有可用锁班类型")
    return PortalMetadata(lock_types, parse_default_reason_prefix(html))


def normalize_lock_type(value: object, metadata: PortalMetadata) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    upper = text.upper()
    if upper in metadata.lock_types:
        return upper
    bracketed = re.search(r"【([^】]+)】", text)
    if bracketed and bracketed.group(1).upper() in metadata.lock_types:
        return bracketed.group(1).upper()
    for code in sorted(metadata.lock_types, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9_/]){re.escape(code)}(?![A-Z0-9_/])", upper):
            return code
    compact = normalize_text(text.replace("(占值勤期类别)", ""))
    matches = [
        code for code, item in metadata.lock_types.items()
        if compact == normalize_text(item.description.replace("(占值勤期类别)", ""))
        or (compact and compact in normalize_text(item.description.replace("(占值勤期类别)", "")))
    ]
    return matches[0] if len(matches) == 1 else ""
