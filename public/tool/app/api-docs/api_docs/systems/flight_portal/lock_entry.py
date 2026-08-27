from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime

from ieb_protocol import IebContractError
from ieb_protocol.lock_metadata import normalize_text
from ieb_protocol.lock_models import EmployeeIdentity, LockSubmission, LockTypeMetadata, PortalMetadata, SubmitResult
from ieb_protocol.lock_protocol import LockProtocol

from ...catalog import EndpointRecord
from .common import required


def option_rows(metadata: PortalMetadata) -> list[dict[str, str]]:
    return [
        {
            "value": item.code,
            "label": item.description,
            "displayLabel": item.label,
            "limitFlag": item.limit_flag,
            "dateSplitFlag": item.date_split_flag,
        }
        for item in metadata.lock_types.values()
    ]


def _clock(value: object, label: str) -> str:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%H:%M").strftime("%H:%M")
    except ValueError as error:
        raise ValueError(f"{label}格式应为 HH:mm") from error


def _submission(
    supplied: dict[str, object],
    identity: EmployeeIdentity,
    item: LockTypeMetadata,
) -> LockSubmission:
    mode = int(required(supplied, "lockTimeType", "时间模式"))
    reason = required(supplied, "lockRemark", "锁班原因")
    if len(reason) > 60:
        raise ValueError("锁班原因不能超过 60 个字符")
    if mode == 1:
        start_text = required(supplied, "startDt", "开始日期时间").replace("T", " ")
        end_text = required(supplied, "endDt", "结束日期时间").replace("T", " ")
        try:
            start = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
            end = datetime.strptime(end_text, "%Y-%m-%d %H:%M")
        except ValueError as error:
            raise ValueError("日期时间格式应为 YYYY-MM-DD HH:mm") from error
        if end <= start:
            raise ValueError("结束日期时间必须晚于开始日期时间")
        return LockSubmission(
            identity.employee_id, item.code, mode,
            start.date().isoformat(), end.date().isoformat(),
            start.strftime("%H:%M"), end.strftime("%H:%M"), "", (), reason,
        )
    if mode != 2 or not item.supports_monthly:
        raise ValueError("当前锁班类型不支持所选时间模式")
    month = required(supplied, "lockYearAndMonth", "锁班月份")
    try:
        year, month_number = (int(part) for part in month.split("-", 1))
        last_day = monthrange(year, month_number)[1]
    except (TypeError, ValueError) as error:
        raise ValueError("锁班月份格式应为 YYYY-MM") from error
    raw_days = supplied.get("lockDaysNum")
    values = raw_days if isinstance(raw_days, list) else re.split(r"[,，\s]+", str(raw_days or ""))
    days = tuple(int(str(value).strip()) for value in values if str(value).strip().isdigit())
    if not days or any(day < 1 or day > last_day for day in days):
        raise ValueError("月份内日期无效或超出所选月份范围")
    start_time = _clock(supplied.get("lockStartHourAndMinute"), "每日开始时间")
    end_time = _clock(supplied.get("lockEndHourAndMinute"), "每日结束时间")
    if end_time <= start_time:
        raise ValueError("每日结束时间必须晚于开始时间")
    return LockSubmission(
        identity.employee_id, item.code, mode, "", "", start_time, end_time,
        f"{year:04d}-{month_number:02d}", days, reason,
    )


def _result_data(result: SubmitResult) -> dict[str, object]:
    result_columns = list(result.result_rows[0].keys()) if result.result_rows else []
    conflict_columns = list(result.conflict_rows[0].keys()) if result.conflict_rows else []
    conflict_count = len(result.conflict_rows)
    result_count = len(result.result_rows)
    statuses = sorted({normalize_text(row.get("锁班状态") or row.get("状态")) for row in result.result_rows} - {""})
    return {
        "summary": {
            "resultCount": result_count,
            "conflictCount": conflict_count,
            "lockStatuses": statuses,
            "outcome": "存在锁班冲突" if conflict_count else "提交成功" if statuses == ["待审批"] else "未返回有效待审批结果",
        },
        "tables": [
            {"id": "results", "title": "普通结果", "columns": result_columns, "rows": result.result_rows},
            {"id": "conflicts", "title": "冲突结果", "columns": conflict_columns, "rows": result.conflict_rows},
        ],
    }


def execute(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: LockProtocol,
) -> tuple[object, dict[str, object]]:
    metadata = protocol.require_metadata()
    item = metadata.lock_types.get(required(supplied, "lockType", "锁班类型"))
    if item is None:
        raise ValueError("所选锁班类型已不存在，请重新载入 Cookie")
    identity = protocol.validate_employee(required(supplied, "staffnum", "员工号"))
    submission = _submission(supplied, identity, item)
    response, result = protocol.submit(submission, identity, item)
    if result.conflict_rows:
        rows, problem = protocol.attribute_result(result, submission, identity, conflicts=True)
        if problem:
            raise IebContractError(problem)
        return response, _result_data(SubmitResult([], rows))
    rows, problem = protocol.attribute_result(result, submission, identity)
    if problem:
        raise IebContractError(problem)
    statuses = {normalize_text(row.get("锁班状态") or row.get("状态")) for row in rows}
    if statuses != {"待审批"}:
        raise IebContractError("门户普通结果已归属，但锁班状态不是待审批")
    return response, _result_data(SubmitResult(rows, []))
