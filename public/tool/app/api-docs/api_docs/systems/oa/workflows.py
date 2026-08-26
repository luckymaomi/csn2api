from __future__ import annotations

import json
import time
from collections import Counter
from typing import Callable

from oa_protocol import OaProtocolClient, OaSessionExpired
from oa_protocol.models import ELIGIBLE_CATEGORY, WaitingRecord

from ...catalog import EndpointRecord


Progress = Callable[[dict[str, object]], None] | None


def _payload(
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


def _count_data(records: list[WaitingRecord]) -> tuple[dict[str, object], dict[str, object]]:
    counts = Counter(item.category for item in records)
    rows = [{
        "模块": category,
        "数量": count,
        "处理方式": "可执行已阅" if category == ELIGIBLE_CATEGORY else "跳过",
    } for category, count in counts.items()]
    eligible = sum(item.eligible for item in records)
    summary = {"total": len(records), "eligible": eligible, "skipped": len(records) - eligible}
    return {
        "summary": summary,
        "tables": [{"id": "categories", "title": "OA 模块数量", "columns": ["模块", "数量", "处理方式"], "rows": rows}],
    }, summary


def execute_count(record: EndpointRecord, protocol: OaProtocolClient) -> dict[str, object]:
    started = time.perf_counter()
    snapshot = protocol.scan_waiting()
    data, summary = _count_data(snapshot.records)
    return _payload(record, started, data, summary, "Local workflow completed")


def _read_payload(
    record: EndpointRecord,
    started: float,
    summary: dict[str, object],
    results: list[dict[str, object]],
    completed: bool,
) -> dict[str, object]:
    data = {
        "summary": dict(summary),
        "tables": [{
            "id": "results", "title": "OA 已阅结果",
            "columns": ["title", "category", "categoryName", "status", "message"],
            "rows": list(results),
        }],
    }
    return _payload(
        record,
        started,
        data,
        {**summary, "results": list(results)},
        "Local workflow completed" if completed else "Local workflow running",
    )


def execute_read(
    record: EndpointRecord,
    supplied: dict[str, object],
    protocol: OaProtocolClient,
    progress: Progress,
) -> dict[str, object]:
    started = time.perf_counter()
    text = str(supplied.get("count") or "").strip()
    if not text.isdigit() or int(text) < 1:
        raise ValueError("已阅数量必须是正整数")
    requested = int(text)
    snapshot = protocol.scan_waiting()
    eligible = [item for item in snapshot.records if item.eligible]
    targets = eligible[:requested]
    results: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "scanned": len(snapshot.records), "eligible": len(eligible),
        "skipped": len(snapshot.records) - len(eligible), "requested": requested,
        "target": len(targets), "success": 0, "failed": 0,
    }
    if progress:
        progress(_read_payload(record, started, summary, results, False))
    for item in targets:
        try:
            protocol.mark_read(item)
        except OaSessionExpired:
            raise
        except Exception as error:
            summary["failed"] = int(summary["failed"]) + 1
            results.append(item.public_result("失败", str(error)))
        else:
            summary["success"] = int(summary["success"]) + 1
            results.append(item.public_result("成功", "已阅接口返回成功"))
        if progress:
            progress(_read_payload(record, started, summary, results, False))
    return _read_payload(record, started, summary, results, True)
