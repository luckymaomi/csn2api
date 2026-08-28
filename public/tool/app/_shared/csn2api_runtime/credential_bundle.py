from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping


BUNDLE_FORMAT = "csn2api-cookie-bundle"
BUNDLE_SCHEMA_VERSION = 1


def create_credential_bundle(credentials: Mapping[str, str]) -> dict[str, object]:
    systems = [
        {"systemId": system_id, "credentials": value}
        for system_id, value in sorted(credentials.items())
        if system_id and value
    ]
    return {
        "format": BUNDLE_FORMAT,
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "systems": systems,
    }


def parse_credential_bundle(
    payload: object,
    *,
    allowed_system_ids: set[str] | None = None,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Cookie 文件必须是 JSON 对象")
    if payload.get("format") != BUNDLE_FORMAT or payload.get("schemaVersion") != BUNDLE_SCHEMA_VERSION:
        raise ValueError("Cookie 文件格式或版本不受支持")
    systems = payload.get("systems")
    if not isinstance(systems, list) or not systems:
        raise ValueError("Cookie 文件没有可导入的系统凭据")

    result: dict[str, str] = {}
    for item in systems:
        if not isinstance(item, dict):
            raise ValueError("Cookie 文件中的系统记录无效")
        system_id = str(item.get("systemId", "") or "").strip()
        credentials = str(item.get("credentials", "") or "").strip()
        if not system_id or not credentials:
            raise ValueError("Cookie 文件中的系统或凭据为空")
        if system_id in result:
            raise ValueError(f"Cookie 文件重复包含系统：{system_id}")
        if allowed_system_ids is not None and system_id not in allowed_system_ids:
            raise ValueError(f"Cookie 文件包含未知系统：{system_id}")
        result[system_id] = credentials
    return result


__all__ = ["create_credential_bundle", "parse_credential_bundle"]
