from __future__ import annotations

import random
import time

from .base import IebContractError, IebSession
from .lock_metadata import normalize_text, parse_portal_metadata
from .lock_models import EmployeeIdentity, LockSubmission, LockTypeMetadata, PortalMetadata, SubmitResult
from .lock_results import (
    attribute_rows,
    parse_query_result,
    parse_quota_result,
    parse_submit_result,
    query_form,
    same_query_identity,
)
from .lock_submission import build_submit_form


ENTRY_PATH = "/newieb/nonproductionTask/showNonproductionTaskImportPage"
EMPLOYEE_PATH = "/newieb/nonproductionTask/vaildStaffNum"
QUOTA_PATH = "/newieb/nonproductionTask/showNonproductionHolidayRulesTips"
SUBMIT_PATH = "/newieb/nonproductionTask/showNonproductionTaskImportResultPage"
QUERY_PATH = "/newieb/nonproductionTask/showLockListPage"
STATE_PATHS = {
    "approve": "/newieb/nonproductionTask/importNonproductionTaskLockListToSoc",
    "withdraw": "/newieb/nonproductionTask/deleteNonproductionTaskLock",
    "unlock": "/newieb/nonproductionTask/unlockNonproductionTaskLock",
    "reject": "/newieb/nonproductionTask/rejectNonproductionTaskLock",
}


def random_value() -> str:
    return f"{random.random():.16f}".rstrip("0")


class LockProtocol:
    """锁班动态元数据、人员校验、提交、查询和状态动作的生产协议。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session
        self.metadata: PortalMetadata | None = None

    def request_metadata(self) -> tuple[object, PortalMetadata]:
        response = self.session.request(
            "GET", ENTRY_PATH, params={"random": random_value()},
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        metadata = parse_portal_metadata(str(response.text or ""))
        self.metadata = metadata
        return response, metadata

    def load_metadata(self) -> tuple[PortalMetadata, dict[str, str]]:
        _response, metadata = self.request_metadata()
        _identity_response, identity = self.session.fetch_identity()
        return metadata, identity

    def check_session(self) -> None:
        self.request_metadata()

    def require_metadata(self) -> PortalMetadata:
        if self.metadata is None:
            raise IebContractError("尚未加载当前动态锁班类型")
        return self.metadata

    def validate_employee(self, employee_id: str) -> EmployeeIdentity:
        staff_number = normalize_text(employee_id)
        if not staff_number:
            raise ValueError("员工号不能为空")
        response = self.session.request(
            "POST", EMPLOYEE_PATH,
            data={"staffNum": staff_number, "operationType": "1", "random": random_value(), "flagType": "nonproductionTask"},
            headers={"Accept": "application/json, text/javascript, */*; q=0.01", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise IebContractError("员工校验响应不是有效 JSON") from error
        if not isinstance(payload, dict) or str(payload.get("permissionFlag", "")).lower() != "true":
            message = normalize_text(payload.get("errorMsg") or payload.get("msg")) if isinstance(payload, dict) else ""
            raise IebContractError(message or f"员工号 {staff_number} 未通过门户校验")
        name, department = normalize_text(payload.get("nameInfo")), normalize_text(payload.get("deptInfo"))
        if not name or not department:
            raise IebContractError("员工校验响应缺少姓名或部门")
        return EmployeeIdentity(staff_number, name, department)

    def request_quota(self, identity: EmployeeIdentity, item: LockTypeMetadata) -> tuple[object, list[str], list[dict[str, str]]]:
        response = self.session.request(
            "POST", QUOTA_PATH,
            data={"staffnum": identity.employee_id, "holidayType": item.code, "holidayTypeDesc": item.description, "random": random_value()},
            headers={"Accept": "text/html, */*; q=0.01", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        headers, rows = parse_quota_result(str(response.text or ""))
        return response, headers, rows

    def submit_form(self, body: list[tuple[str, str]]) -> tuple[object, SubmitResult]:
        response = self.session.request(
            "POST", SUBMIT_PATH, data=body,
            headers={"Accept": "text/html, */*; q=0.01", "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        )
        return response, parse_submit_result(str(response.text or ""))

    def submit(self, submission: LockSubmission, identity: EmployeeIdentity, item: LockTypeMetadata) -> tuple[object, SubmitResult]:
        return self.submit_form(build_submit_form(submission, identity, item, random_value))

    def attribute_result(
        self,
        result: SubmitResult,
        submission: LockSubmission,
        identity: EmployeeIdentity,
        *,
        conflicts: bool = False,
    ) -> tuple[list[dict[str, str]], str]:
        metadata = self.require_metadata()
        if conflicts:
            if not result.conflict_rows:
                return [], "门户没有返回冲突结果"
            return attribute_rows(result.conflict_rows, submission, identity, metadata, "冲突结果")
        if result.conflict_rows:
            return [], "门户返回冲突结果"
        if not result.result_rows:
            return [], "门户没有返回普通结果"
        return attribute_rows(result.result_rows, submission, identity, metadata, "提交结果")

    def query_records(self, employee_id: str, status: str) -> list[dict[str, str]]:
        first_form = query_form(employee_id, status, 1, random_value())
        first = self.session.request("POST", QUERY_PATH, data=first_form, headers={"Accept": "text/html, */*; q=0.01"})
        rows, page_count = parse_query_result(str(first.text or ""))
        for page in range(2, page_count + 1):
            params = query_form(employee_id, status, page, random_value())
            params.pop("random", None)
            params["currentStr"] = str(int(time.time() * 1000))
            response = self.session.request("GET", QUERY_PATH, params=params, headers={"Accept": "text/html, */*; q=0.01"})
            page_rows, returned_pages = parse_query_result(str(response.text or ""))
            if returned_pages > page_count:
                raise IebContractError("锁班查询分页总数在遍历中发生变化")
            rows.extend(page_rows)
        unique: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            record_id = normalize_text(row.get("记录ID"))
            if record_id and record_id in seen:
                continue
            if record_id:
                seen.add(record_id)
            unique.append(row)
        return unique

    def perform_state_action(self, action: str, rows: list[dict[str, str]], reason: str) -> str:
        if action not in STATE_PATHS or not rows:
            raise IebContractError("状态动作或目标记录无效")
        ids = [normalize_text(row.get("记录ID")) for row in rows]
        if any(not record_id for record_id in ids):
            raise IebContractError("目标记录缺少记录 ID")
        employee_id = normalize_text(rows[0].get("员工号"))
        if not employee_id or any(normalize_text(row.get("员工号")) != employee_id for row in rows):
            raise IebContractError("状态动作目标必须属于同一员工")
        data = [("ids", record_id) for record_id in ids]
        data.append(("approveRemark", reason))
        data.extend(query_form(employee_id, "", 1, random_value()).items())
        response = self.session.request("POST", STATE_PATHS[action], data=data, headers={"Accept": "application/json, text/javascript, */*; q=0.01"})
        try:
            payload = response.json()
        except ValueError as error:
            raise IebContractError("状态动作响应不是有效 JSON") from error
        if not isinstance(payload, dict) or str(payload.get("success", "")).lower() != "true":
            message = normalize_text(payload.get("errorMsg")) if isinstance(payload, dict) else ""
            raise IebContractError(message or "门户状态动作失败")
        return normalize_text(payload.get("successMsg")) or "门户状态动作成功"

    def approve_records(self, rows: list[dict[str, str]], reason: str) -> str:
        message = self.perform_state_action("approve", rows, reason)
        employee_id = normalize_text(rows[0].get("员工号"))
        locked, pending = self.query_records(employee_id, "已锁"), self.query_records(employee_id, "待审批")
        if any(not any(same_query_identity(candidate, row) for candidate in locked) for row in rows):
            raise IebContractError("门户提示通过成功，但目标未在已锁列表中精确找到")
        if any(any(same_query_identity(candidate, row) for candidate in pending) for row in rows):
            raise IebContractError("通过后目标仍出现在待审批列表")
        return message
