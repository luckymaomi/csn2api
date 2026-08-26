from __future__ import annotations

import random
import time

from ...catalog import EndpointRecord


def random_keepalive_interval() -> int:
    return random.randint(30, 60)


def required(supplied: dict[str, object], name: str, label: str) -> str:
    value = str(supplied.get(name, "") or "").strip()
    if not value:
        raise ValueError(f"请填写{label}")
    return value


def response_payload(
    record: EndpointRecord,
    response: object,
    started: float,
    data: dict[str, object],
) -> dict[str, object]:
    response_headers = getattr(response, "headers", {})
    headers = {
        name: value
        for name, value in response_headers.items()
        if str(name).lower() not in {"set-cookie", "cookie"}
    }
    content = bytes(getattr(response, "content", b"") or b"")
    text = str(getattr(response, "text", "") or "")
    return {
        "endpointId": record.full_id,
        "method": record.endpoint["method"],
        "status": getattr(response, "status_code", 0),
        "reason": getattr(response, "reason", ""),
        "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
        "finalUrl": str(getattr(response, "url", "") or record.url),
        "contentType": response_headers.get("Content-Type", ""),
        "headers": headers,
        "data": data,
        "body": "" if content.startswith(b"PK") else text,
    }
