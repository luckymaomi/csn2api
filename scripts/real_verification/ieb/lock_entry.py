from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, serve_app, verify_frontend_route
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-lock-entry-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    if not verifier.allow_write or not verifier.lock_confirmation:
        verifier.record("ieb", "api.lock-entry.submit", "SKIP", "未提供本轮写操作显式确认")
        return
    expected = "|".join(
        verifier.input(name)
        for name in ("lockStaffNumber", "lockType", "lockStartDate", "lockEndDate", "lockRemark")
    )
    if verifier.lock_confirmation != expected:
        verifier.record("ieb", "api.lock-entry.submit", "SKIP", "锁班确认串与授权对象、日期、类型、备注不完全一致", write=True)
        return
    options = executor.load_options("lock-types")
    lock_type = verifier.input("lockType")
    item = next(
        (row for row in options if lock_type in str(row.get("label", "")) or lock_type in str(row.get("displayLabel", ""))),
        None,
    )
    if not item:
        verifier.record("ieb", "api.lock-entry.submit", "FAIL", "动态锁班类型中没有本轮授权类型", write=True)
        return
    def submit() -> object:
        value = executor.execute(
            "lock-entry.submit",
            {
                "staffnum": verifier.input("lockStaffNumber"),
                "lockType": item["value"],
                "lockTimeType": "1",
                "startDt": f"{verifier.input('lockStartDate')}T08:59",
                "endDt": f"{verifier.input('lockEndDate')}T19:59",
                "lockRemark": verifier.input("lockRemark"),
            },
        )
        data = value.get("data") if isinstance(value, dict) else None
        summary = data.get("summary") if isinstance(data, dict) else None
        if not isinstance(summary, dict) or summary.get("outcome") != "提交成功":
            raise RuntimeError("锁班响应没有通过业务成功契约")
        return value

    submitted = verifier.call(
        "ieb",
        "api.lock-entry.submit",
        submit,
        write=True,
        detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
    )
    if submitted is None or "ieb" in verifier.halted:
        return

    def approve() -> object:
        value = executor.execute(
            "lock-entry.approve-pending",
            {
                "staffnum": verifier.input("lockStaffNumber"),
                "lockType": item["value"],
                "lockTimeType": "1",
                "startDt": f"{verifier.input('lockStartDate')}T08:59",
                "endDt": f"{verifier.input('lockEndDate')}T19:59",
                "lockRemark": verifier.input("lockRemark"),
            },
        )
        data = value.get("data") if isinstance(value, dict) else None
        summary = data.get("summary") if isinstance(data, dict) else None
        if not isinstance(summary, dict) or summary.get("outcome") != "通过成功" or summary.get("lockStatuses") != ["已锁"]:
            raise RuntimeError("锁班通过响应没有通过已锁回查业务成功契约")
        return value

    verifier.call(
        "ieb",
        "api.lock-entry.approve-pending",
        approve,
        write=True,
        detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
    )


def verify_app(verifier: Any) -> None:
    from http_lock_entry.manager import RunManager
    from http_lock_entry.server import create_server

    try:
        fields = [
            verifier.input("lockStaffNumber"),
            verifier.inputs.get("iebStaffName", ""),
            verifier.input("lockType"),
            verifier.input("lockStartDate"),
            verifier.input("lockEndDate"),
            "",
            "",
            verifier.input("lockRemark"),
        ]
        with TemporaryDirectory(prefix="csn2api-real-lock-") as directory:
            manager = RunManager(Path(directory))
            server = create_server(APP_ROOT, 0, manager)
            with serve_app(server, manager) as base_url:
                verify_frontend_route(base_url, "/api/check-data")
                session = post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["ieb"]})
                state = post_json(
                    base_url,
                    "/api/check-data",
                    {"inputMode": "paste", "pastedText": "|".join(fields)},
                )
        checks = state.get("checks", {})
        data = checks.get("data", {}) if isinstance(checks, dict) else {}
        if not isinstance(data, dict) or not data.get("ok") or int(data.get("validCount") or 0) != 1:
            raise RuntimeError("APP 锁班检查数据路由没有确认唯一有效记录")
        verifier.record("ieb", "app.lock-entry.preflight", "PASS", f"前端 /api/check-data 已接通，动态类型 {session.get('session', {}).get('typeCount', 0)} 项")
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "app.lock-entry.preflight", error)
