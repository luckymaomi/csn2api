from __future__ import annotations


ROW_KEYS = ("resultMyBoxItems", "resultList", "rows", "records", "list", "content", "items")
TOTAL_KEYS = ("totalRecordCount", "totalCount", "total", "recordsTotal", "totalElements")


class OaProtocolError(RuntimeError):
    pass


class OaContractError(OaProtocolError):
    pass


class OaBusinessError(OaProtocolError):
    pass


class OaSessionExpired(OaProtocolError):
    pass


def parse_business_payload(response: object, action: str) -> dict[str, object]:
    status = int(getattr(response, "status_code", 0) or 0)
    if status in {301, 302, 303, 307, 308}:
        raise OaSessionExpired("OA 登录会话已失效，请重新复制 /oai/work/box/query/waiting 请求")
    if status != 200:
        raise OaProtocolError(f"{action}返回 HTTP {status}")
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except (ValueError, TypeError) as error:
        raise OaContractError(f"{action}没有返回 JSON") from error
    if not isinstance(payload, dict):
        raise OaContractError(f"{action}响应结构不是对象")
    code = str(payload.get("code") or "")
    if code == "301":
        raise OaSessionExpired("OA 登录会话已失效，请重新复制 /oai/work/box/query/waiting 请求")
    if code != "200":
        raise OaBusinessError(f"{action}业务码不是 200")
    return payload


def parse_identity(payload: dict[str, object]) -> dict[str, str]:
    data = payload.get("data")
    user = data.get("loginUserInfo") if isinstance(data, dict) else None
    if not isinstance(user, dict):
        raise OaContractError("OA 用户信息没有返回可识别的当前登录人")
    staff_number = " ".join(str(user.get("empId") or "").split())
    name = " ".join(str(user.get("empName") or "").split())
    if not staff_number or not name:
        raise OaContractError("OA 用户信息没有返回可识别的当前登录人")
    return {"staffNumber": staff_number, "name": name}


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def find_page_contract(value: object) -> tuple[list[object], int | None] | None:
    if not isinstance(value, dict):
        return None
    for key in ROW_KEYS:
        if key not in value:
            continue
        rows = value.get(key)
        total = next((_non_negative_integer(value.get(name)) for name in TOTAL_KEYS if name in value), None)
        if isinstance(rows, list):
            return rows, total
        if rows is None and total == 0:
            return [], 0
    for candidate in value.values():
        found = find_page_contract(candidate)
        if found is not None:
            return found
    return None


def find_total(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in TOTAL_KEYS:
        if key in value and (total := _non_negative_integer(value.get(key))) is not None:
            return total
    for candidate in value.values():
        if (total := find_total(candidate)) is not None:
            return total
    return None
