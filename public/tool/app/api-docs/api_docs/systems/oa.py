from __future__ import annotations

import copy
import json
import time
from collections import Counter
from dataclasses import dataclass
from threading import RLock
from typing import Callable

import requests

from ..catalog import ApiCatalog, EndpointRecord
from ..credentials import (
    all_credential_summary,
    format_all_credentials,
    parse_all_credentials,
    parse_browser_user_agent,
    parse_waiting_template,
)
from .errors import ExecutionError, SessionExpiredError
from .session_keepalive import SessionKeepAlive


ELIGIBLE_CATEGORY = "DOC/official-document"
PAGE_SIZE = 100
ROW_KEYS = ("resultMyBoxItems", "resultList", "rows", "records", "list", "content", "items")
TOTAL_KEYS = ("totalRecordCount", "totalCount", "total", "recordsTotal", "totalElements")


@dataclass(frozen=True)
class WaitingRecord:
    file_id: str
    title: str
    file_type_id: str
    step_item_id: str
    main_category_code: str
    sub_category_code: str
    category_name: str

    @property
    def category(self) -> str:
        return f"{self.main_category_code}/{self.sub_category_code}"

    @property
    def eligible(self) -> bool:
        return self.category == ELIGIBLE_CATEGORY

    @classmethod
    def from_payload(cls, payload: object) -> "WaitingRecord":
        if not isinstance(payload, dict):
            raise ExecutionError("待办记录结构不是对象")
        clean = lambda value: " ".join(str(value or "").split())
        record = cls(
            file_id=clean(payload.get("fileId")),
            title=clean(payload.get("fileTitle")),
            file_type_id=clean(payload.get("fileTypeId")),
            step_item_id=clean(payload.get("stepItemId")),
            main_category_code=clean(payload.get("moduleMainCategoryCode")),
            sub_category_code=clean(payload.get("moduleSubCategoryCode")),
            category_name=clean(payload.get("moduleSubCategoryName")),
        )
        if not record.file_id or not record.title:
            raise ExecutionError("待办记录缺少内部标识或标题")
        if not record.main_category_code or not record.sub_category_code:
            raise ExecutionError("待办记录缺少模块分类")
        if record.eligible and (not record.file_type_id or not record.step_item_id):
            raise ExecutionError("公文待办缺少已阅所需字段")
        return record

    def public_result(self, status: str, message: str) -> dict[str, object]:
        return {
            "title": self.title,
            "category": self.category,
            "categoryName": self.category_name,
            "status": status,
            "message": message,
        }


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        parsed = int(value)
        return parsed if parsed >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _find_page_contract(value: object) -> tuple[list[object], int | None] | None:
    if not isinstance(value, dict):
        return None
    for row_key in ROW_KEYS:
        if row_key not in value:
            continue
        rows = value.get(row_key)
        total = next(
            (_non_negative_integer(value.get(key)) for key in TOTAL_KEYS if key in value),
            None,
        )
        if isinstance(rows, list):
            return rows, total
        if rows is None and total == 0:
            return [], 0
    for candidate in value.values():
        found = _find_page_contract(candidate)
        if found is not None:
            return found
    return None


def _find_total(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in TOTAL_KEYS:
        if key in value:
            total = _non_negative_integer(value.get(key))
            if total is not None:
                return total
    for candidate in value.values():
        found = _find_total(candidate)
        if found is not None:
            return found
    return None


class OaAdapter:
    """维护 OA 独立会话，并执行待办查询和按数量已阅工作流。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        session_factory: Callable[[], requests.Session] = requests.Session,
        timeout_seconds: int = 30,
        keepalive_interval_factory: Callable[[], int] = lambda: 30,
    ) -> None:
        self.catalog = catalog
        self.session_factory = session_factory
        self.timeout_seconds = timeout_seconds
        self.session: requests.Session | None = None
        self.cookies: dict[str, str] = {}
        self.waiting_template: dict[str, object] | None = None
        self.request_lock = RLock()
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout_seconds,
            "oa-cookie-keepalive",
        )

    def load_credentials(self, source: str) -> dict[str, object]:
        cookies = parse_all_credentials(source)
        user_agent = parse_browser_user_agent(source)
        waiting_template = parse_waiting_template(source)
        session = self.session_factory()
        session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            ),
        })
        for name, value in cookies.items():
            session.cookies.set(name, value, domain="work.csair.com", path="/")

        self.clear_credentials()
        with self.request_lock:
            self.cookies = cookies
            self.session = session
            self.waiting_template = waiting_template
        try:
            self._check_session()
        except Exception:
            self.clear_credentials()
            raise
        self.keepalive.record_success()
        self.keepalive.start(self._check_session)
        return {
            **self.session_status(),
            "credentials": format_all_credentials(cookies),
        }

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        with self.request_lock:
            self._clear_session_state()

    def session_status(self) -> dict[str, object]:
        with self.request_lock:
            return {
                **all_credential_summary(self.cookies),
                "keepAlive": self.keepalive.status(bool(self.cookies)),
            }

    def execute(
        self,
        record: EndpointRecord,
        supplied: dict[str, object],
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        if record.full_id == "oa-read.count":
            return self._execute_count_workflow(record)
        if record.full_id == "oa-read.read":
            return self._execute_read_workflow(record, supplied, progress_callback)
        raise ExecutionError("当前系统不支持该业务接口")

    def _execute_count_workflow(self, record: EndpointRecord) -> dict[str, object]:
        started = time.perf_counter()
        records = self._scan_waiting()
        category_counts = Counter(item.category for item in records)
        rows = [
            {
                "模块": category,
                "数量": count,
                "处理方式": "可执行已阅" if category == ELIGIBLE_CATEGORY else "跳过",
            }
            for category, count in category_counts.items()
        ]
        eligible = sum(1 for item in records if item.eligible)
        summary = {
            "total": len(records),
            "eligible": eligible,
            "skipped": len(records) - eligible,
        }
        data = {
            "summary": summary,
            "tables": [{
                "id": "categories",
                "title": "OA 模块数量",
                "columns": ["模块", "数量", "处理方式"],
                "rows": rows,
            }],
        }
        return self._local_workflow_payload(record, started, data, summary, "Local workflow completed")

    def _execute_read_workflow(
        self,
        record: EndpointRecord,
        supplied: dict[str, object],
        progress_callback: Callable[[dict[str, object]], None] | None,
    ) -> dict[str, object]:
        started = time.perf_counter()
        requested = self._integer(supplied.get("count", ""), "已阅数量")
        records = self._scan_waiting()
        eligible = [item for item in records if item.eligible]
        targets = eligible[:requested]
        results: list[dict[str, object]] = []
        success = 0
        failed = 0
        summary = {
            "scanned": len(records),
            "eligible": len(eligible),
            "skipped": len(records) - len(eligible),
            "requested": requested,
            "target": len(targets),
            "success": success,
            "failed": failed,
        }
        if progress_callback is not None:
            progress_callback(self._read_progress_payload(record, started, summary, results))

        for item in targets:
            try:
                self._mark_read(item)
            except Exception as error:
                failed += 1
                results.append(item.public_result("失败", str(error)))
                summary.update({"success": success, "failed": failed})
                if progress_callback is not None:
                    progress_callback(self._read_progress_payload(record, started, summary, results))
                break
            success += 1
            results.append(item.public_result("成功", "已阅接口返回成功"))
            summary.update({"success": success, "failed": failed})
            if progress_callback is not None:
                progress_callback(self._read_progress_payload(record, started, summary, results))

        return self._read_progress_payload(record, started, summary, results, completed=True)

    def _read_progress_payload(
        self,
        record: EndpointRecord,
        started: float,
        summary: dict[str, object],
        results: list[dict[str, object]],
        *,
        completed: bool = False,
    ) -> dict[str, object]:
        data = {
            "summary": dict(summary),
            "tables": [{
                "id": "results",
                "title": "OA 已阅结果",
                "columns": ["title", "category", "categoryName", "status", "message"],
                "rows": list(results),
            }],
        }
        body = {**summary, "results": list(results)}
        reason = "Local workflow completed" if completed else "Local workflow running"
        return self._local_workflow_payload(record, started, data, body, reason)

    @staticmethod
    def _local_workflow_payload(
        record: EndpointRecord,
        started: float,
        data: dict[str, object],
        body: dict[str, object],
        reason: str,
    ) -> dict[str, object]:
        return {
            "endpointId": record.full_id,
            "method": record.endpoint["method"],
            "status": 200,
            "reason": reason,
            "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": "/api/execute",
            "contentType": "application/json; charset=utf-8",
            "headers": {},
            "data": data,
            "body": json.dumps(body, ensure_ascii=False),
        }

    def _scan_waiting(self) -> list[WaitingRecord]:
        records: list[WaitingRecord] = []
        seen: set[tuple[str, str]] = set()
        page_index = 0
        while True:
            _response, _payload, page_records, total = self._query_waiting_page(page_index, PAGE_SIZE)
            if not page_records:
                break
            added = 0
            for item in page_records:
                key = (item.file_id, item.step_item_id)
                if key not in seen:
                    seen.add(key)
                    records.append(item)
                    added += 1
            if total is not None and len(records) >= total:
                break
            if len(page_records) < PAGE_SIZE or added == 0:
                break
            page_index += 1
        return records

    def _query_waiting_page(
        self,
        page_index: int,
        page_size: int,
    ) -> tuple[requests.Response, dict[str, object], list[WaitingRecord], int | None]:
        request = self.catalog.get_internal_request("oa-read.waiting-query")
        body = copy.deepcopy(self.waiting_template) if self.waiting_template else {}
        body.pop("moduleMainCategoryId", None)
        body.update({
            "offsetPageIndex": page_index,
            "pageMode": "page",
            "resultCountPerPage": page_size,
        })
        response, payload = self._request_business(request, json_body=body, action="查询 OA 待办")
        contract = _find_page_contract(payload)
        if contract is None:
            raise ExecutionError("待办响应中没有可识别的记录数组")
        rows, local_total = contract
        total = local_total if local_total is not None else _find_total(payload)
        return response, payload, [WaitingRecord.from_payload(item) for item in rows], total

    def _mark_read(self, record: WaitingRecord) -> None:
        request = self.catalog.get_internal_request("oa-read.have-read")
        self._request_business(
            request,
            json_body={
                "approveOpinionType": None,
                "approveOpinionContent": None,
                "docId": record.file_id,
                "docType": record.file_type_id,
                "flowStepId": record.step_item_id,
            },
            action="提交 OA 已阅",
        )

    def _check_session(self) -> None:
        request = self.catalog.get_internal_request("oa-read.user-info")
        self._request_business(request, action="验证 OA Cookie")

    def _request_business(
        self,
        record: EndpointRecord,
        *,
        json_body: dict[str, object] | None = None,
        action: str,
    ) -> tuple[requests.Response, dict[str, object]]:
        response = self._request(
            str(record.endpoint["method"]),
            record.url,
            json_body=json_body,
            headers=self._record_headers(record),
        )
        if response.status_code in {301, 302, 303, 307, 308}:
            self._expire_session()
            raise SessionExpiredError("OA Cookie 已失效，请重新复制 waiting 请求")
        if response.status_code != 200:
            raise ExecutionError(f"{action}返回 HTTP {response.status_code}")
        try:
            payload = json.loads(str(response.text or ""))
        except json.JSONDecodeError as error:
            raise ExecutionError(f"{action}没有返回 JSON") from error
        if not isinstance(payload, dict):
            raise ExecutionError(f"{action}响应结构不是对象")
        code = str(payload.get("code", ""))
        if code == "301":
            self._expire_session()
            raise SessionExpiredError("OA Cookie 已失效，请重新复制 waiting 请求")
        if code != "200":
            raise ExecutionError(f"{action}业务码不是 200")
        return response, payload

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        with self.request_lock:
            if self.session is None or not self.cookies:
                raise SessionExpiredError("请先载入有效 OA Cookie")
            try:
                return self.session.request(
                    method=method,
                    url=url,
                    json=json_body,
                    headers=headers or {},
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                raise ExecutionError("连接 OA 失败") from error

    def _expire_session(self) -> None:
        with self.request_lock:
            self._clear_session_state()
        self.keepalive.mark_expired()

    def _clear_session_state(self) -> None:
        self.cookies = {}
        self.waiting_template = None
        if self.session is not None:
            self.session.close()
            self.session = None

    @staticmethod
    def _integer(value: object, label: str, minimum: int = 1) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label}必须是正整数")
        text = str(value).strip()
        if not text.isdigit() or int(text) < minimum:
            requirement = "非负整数" if minimum == 0 else "正整数"
            raise ValueError(f"{label}必须是{requirement}")
        return int(text)

    @staticmethod
    def _record_headers(record: EndpointRecord) -> dict[str, str]:
        return {
            str(header.get("name")): str(header.get("value"))
            for header in [*record.module.get("commonHeaders", []), *record.endpoint.get("headers", [])]
            if isinstance(header, dict) and header.get("name")
        }

    @staticmethod
    def _response_payload(
        record: EndpointRecord,
        response: requests.Response,
        started: float,
        data: dict[str, object],
    ) -> dict[str, object]:
        headers = {
            name: value
            for name, value in response.headers.items()
            if name.lower() not in {"set-cookie", "cookie"}
        }
        return {
            "endpointId": record.full_id,
            "method": record.endpoint["method"],
            "status": response.status_code,
            "reason": response.reason,
            "elapsedMilliseconds": round((time.perf_counter() - started) * 1000),
            "finalUrl": str(response.url or record.url),
            "contentType": response.headers.get("Content-Type", ""),
            "headers": headers,
            "data": data,
            "body": str(response.text or ""),
        }

    def close(self) -> None:
        self.clear_credentials()


__all__ = ["OaAdapter"]
