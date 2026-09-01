from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-flight-detail-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    staff_number = verifier.input("iebStaffNumber")
    staff_name = verifier.inputs.get("iebStaffName", "")
    month = verifier.input("flightDetailMonth")
    verifier.call(
        "ieb",
        "api.flight-detail.query-month",
        lambda: executor.execute("flight-detail.query-month", {"staffNum": staff_number, "staffName": staff_name, "startStr": month}),
        detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
    )


def verify_app(verifier: Any) -> None:
    from http_flight_detail.manager import RunManager
    from http_flight_detail.server import create_server

    try:
        staff_number = verifier.input("iebStaffNumber")
        staff_name = verifier.inputs.get("iebStaffName", "")
        start_month = verifier.input("flightDetailMonth")
        with TemporaryDirectory(prefix="csn2api-real-flight-detail-") as directory:
            manager = RunManager(Path(directory))
            server = create_server(APP_ROOT, 0, manager)
            with serve_app(server, manager) as base_url:
                verify_frontend_route(base_url, "/api/run")
                post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["ieb"]})
                post_json(base_url, "/api/run", {"inputMode": "paste", "pastedText": f"员工号\t姓名\t开始年月\t结束年月\n{staff_number}\t{staff_name}\t{start_month}\t{start_month}"})
                state = require_completed(wait_for_final(base_url))
                results = state.get("results")
                if not isinstance(results, list) or not results:
                    raise RuntimeError("APP 未返回逐月结果")
                if not any(int(item.get("航班数量", len(item.get("rows", [])))) >= 0 for item in results if isinstance(item, dict)):
                    raise RuntimeError("APP 逐月结果结构无效")
        progress = state.get("progress", {})
        verifier.record("ieb", "app.flight-detail.query-month", "PASS", f"前端 /api/run 已接通，成功 {progress.get('success', 0)} 个人员/月")
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "app.flight-detail.query-month", error)

