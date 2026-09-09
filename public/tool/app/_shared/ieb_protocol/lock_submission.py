from __future__ import annotations

from datetime import date
from typing import Callable

from .base import IebContractError
from .lock_metadata import normalize_text
from .lock_models import EmployeeIdentity, LockSubmission, LockTypeMetadata, PortalMetadata


def resolve_lock_reason(
    metadata: PortalMetadata,
    item: LockTypeMetadata,
    *candidates: object,
) -> str:
    reason = next((text for value in candidates if (text := normalize_text(value))), "")
    if not reason:
        reason = f"{metadata.default_reason_prefix}{item.description}"
    if not reason or len(reason) > 60:
        raise IebContractError("锁班原因不能为空且不能超过60个字符")
    return reason


def build_submit_form(
    submission: LockSubmission,
    identity: EmployeeIdentity,
    item: LockTypeMetadata,
    random_value: Callable[[], str],
) -> list[tuple[str, str]]:
    if submission.employee_id != identity.employee_id or submission.lock_type != item.code:
        raise IebContractError("锁班提交对象与动态元数据归属不一致")
    if not submission.reason or len(submission.reason) > 60:
        raise IebContractError("锁班原因不能为空且不能超过60个字符")
    if submission.time_mode == 1:
        try:
            lock_days = (date.fromisoformat(submission.end_date) - date.fromisoformat(submission.start_date)).days + 1
        except ValueError as error:
            raise IebContractError("连续时间段日期格式无效") from error
        if lock_days < 1:
            raise IebContractError("结束日期不能早于开始日期")
        timing = [
            ("startDt", f"{submission.start_date} {submission.start_time}"),
            ("endDt", f"{submission.end_date} {submission.end_time}"),
            ("lockDays", str(lock_days)), ("lockTimeType", "1"),
            ("lockYearAndMonth", ""), ("lockStartHourAndMinute", ""), ("lockEndHourAndMinute", ""),
        ]
    elif submission.time_mode == 2:
        if not item.supports_monthly or not submission.month or not submission.days:
            raise IebContractError("当前锁班类型或输入不支持按月份提交")
        timing = [
            ("startDt", ""), ("endDt", ""), ("lockDays", str(len(submission.days))),
            ("lockTimeType", "2"), ("lockYearAndMonth", submission.month),
            *(("lockDaysNum", str(day)) for day in submission.days),
            ("lockStartHourAndMinute", submission.start_time),
            ("lockEndHourAndMinute", submission.end_time),
        ]
    else:
        raise IebContractError(f"不支持的时间模式 {submission.time_mode}")
    return [
        ("staffnum", identity.employee_id), ("lockType", item.code),
        ("dateSplitFlag", item.date_split_flag), ("lockRemark", submission.reason),
        *timing, ("lockTypeDesc", item.description), ("chnName", identity.name),
        ("orgUnitName", identity.department), ("random", random_value()),
    ]
