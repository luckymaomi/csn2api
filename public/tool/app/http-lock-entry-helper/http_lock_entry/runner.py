"""Strictly serial orchestration for direct HTTP lock entry."""

from __future__ import annotations

import threading
from typing import Callable

from .metadata import normalize_text
from .portal_client import PortalClient, PortalError, PortalSessionExpired
from .result_store import ResultStore


EventCallback = Callable[[dict[str, object]], None]


class BatchRunner:
    def __init__(
        self,
        client: PortalClient,
        store: ResultStore,
        common_reason: str,
        stop_event: threading.Event,
        emit: EventCallback | None = None,
        approve_after_submit: bool = False,
    ):
        self.client = client
        self.store = store
        self.common_reason = common_reason
        self.stop_event = stop_event
        self.emit = emit or (lambda _event: None)
        self.approve_after_submit = bool(approve_after_submit)

    def _log(self, level: str, message: str) -> None:
        self.emit({"type": "log", "level": level, "message": message})

    def _result_row(
        self,
        index: int,
        record: dict[str, object],
        identity_name: str,
        status: str,
        *,
        portal_row: dict[str, str] | None = None,
        remark: str = "",
        conflict_reason: str = "",
        message: str = "",
    ) -> dict[str, object]:
        portal_row = portal_row or {}
        start_value = normalize_text(portal_row.get("开始日期") or portal_row.get("开始时间"))
        end_value = normalize_text(portal_row.get("结束日期") or portal_row.get("结束时间"))
        if not start_value:
            if int(record.get("时间模式", 1)) == 1:
                start_value = f"{record.get('开始日期', '')} {record.get('开始时间', '')}"
                end_value = f"{record.get('结束日期', '')} {record.get('结束时间', '')}"
            else:
                start_value = f"{record.get('月份', '')} {record.get('日期列表', '')} {record.get('开始时间', '')}"
                end_value = f"{record.get('月份', '')} {record.get('日期列表', '')} {record.get('结束时间', '')}"
        metadata = self.client.metadata
        type_code = str(record.get("请假类型", ""))
        type_item = metadata.lock_types.get(type_code) if metadata else None
        type_name = type_item.description if type_item else type_code
        return {
            "type": "record_result",
            "index": index,
            "sourceRow": record.get("来源行", ""),
            "employeeId": record.get("员工号", ""),
            "expectedName": record.get("姓名", "") or "",
            "name": identity_name,
            "inputType": type_name,
            "actualType": type_name,
            "inputStartDate": record.get("开始日期", ""),
            "inputEndDate": record.get("结束日期", ""),
            "actualStartDateTime": start_value,
            "actualEndDateTime": end_value,
            "timeMode": record.get("时间模式", 1),
            "status": status,
            "portalStatus": normalize_text(portal_row.get("锁班结果") or portal_row.get("锁班状态")),
            "conflictReason": conflict_reason,
            "remark": remark,
            "message": message,
        }

    def _persist_and_emit(self, row: dict[str, object]) -> None:
        self.store.append(row)
        self.emit(row)

    def _complete_success(
        self,
        index: int,
        record: dict[str, object],
        identity_name: str,
        rows: list[dict[str, str]],
        reason: str,
    ) -> bool:
        for row in rows:
            self._persist_and_emit(self._result_row(
                index,
                record,
                identity_name,
                "成功",
                portal_row=row,
                remark=reason,
            ))
        if not self.approve_after_submit:
            return True
        try:
            message = self.client.approve_records(rows, reason)
        except Exception as error:
            self._persist_and_emit(self._result_row(
                index,
                record,
                identity_name,
                "通过失败",
                portal_row=rows[0],
                remark=reason,
                message=f"待审批记录已生成，但通过并锁班失败：{error}",
            ))
            return False
        for row in rows:
            locked_row = dict(row)
            locked_row["锁班状态"] = "已锁"
            locked_row["状态"] = "已锁"
            self._persist_and_emit(self._result_row(
                index,
                record,
                identity_name,
                "已通过并锁班",
                portal_row=locked_row,
                remark=reason,
                message=message,
            ))
        return True

    def _submit_record(
        self,
        index: int,
        record: dict[str, object],
        identity: object,
    ) -> bool:
        metadata = self.client.require_metadata()
        item = metadata.lock_types.get(str(record.get("请假类型", "")))
        if item is None:
            raise PortalError("当前记录的锁班类型不在动态类型列表中")
        reason = self.client.resolve_reason(record, self.common_reason)
        body = self.client.build_submit_data(record, identity, item, reason)
        result = self.client.submit(body)
        rows, problem = self.client.attribute_submit_result(result, record, identity)
        if rows:
            return self._complete_success(index, record, identity.name, rows, reason)

        if not result.conflict_rows:
            self._persist_and_emit(self._result_row(
                index,
                record,
                identity.name,
                "失败",
                remark=reason,
                message=problem,
            ))
            return False

        conflict_rows, conflict_problem = self.client.attribute_conflict_result(result, record, identity)
        portal_row = conflict_rows[0] if conflict_rows else result.conflict_rows[0]
        conflict_reason = normalize_text(portal_row.get("冲突"))
        self._persist_and_emit(self._result_row(
            index,
            record,
            identity.name,
            "冲突",
            portal_row=portal_row,
            remark=reason,
            conflict_reason=conflict_reason,
            message=conflict_problem,
        ))
        return False

    def run(self, records: list[dict[str, object]]) -> dict[str, int | bool]:
        summary: dict[str, int | bool] = {
            "total": len(records),
            "completed": 0,
            "success": 0,
            "failed": 0,
            "stopped": False,
        }
        self.emit({"type": "progress", **summary, "current": ""})
        for index, record in enumerate(records, start=1):
            if self.stop_event.is_set():
                summary["stopped"] = True
                break
            current = f"{record.get('员工号', '')} {record.get('姓名', '') or ''}".strip()
            self.emit({"type": "progress", **summary, "current": current})
            record_success = True
            try:
                identity = self.client.validate_employee(str(record.get("员工号", "")))
                expected_name = normalize_text(record.get("姓名"))
                if expected_name and expected_name != normalize_text(identity.name):
                    self._log("warning", f"{record.get('员工号')} 输入姓名与门户姓名不一致，按门户身份提交")
                record_success = self._submit_record(index, record, identity)
            except PortalSessionExpired:
                raise
            except Exception as error:
                record_success = False
                self._persist_and_emit(self._result_row(
                    index,
                    record,
                    "",
                    "失败",
                    message=str(error),
                    remark=normalize_text(record.get("备注")) or self.common_reason,
                ))
                self._log("error", f"{current} 处理失败：{error}")
            summary["completed"] = int(summary["completed"]) + 1
            key = "success" if record_success else "failed"
            summary[key] = int(summary[key]) + 1
            self.emit({"type": "progress", **summary, "current": ""})
        return summary
