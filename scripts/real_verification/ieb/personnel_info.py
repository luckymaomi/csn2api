from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-qualification-query-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    staff_number = verifier.input("iebStaffNumber")
    for endpoint, key in (
        ("personnel-info.basic", "staffNum"),
        ("personnel-info.technical", "staffNum"),
        ("personnel-info.operation", "empid"),
        ("personnel-info.training-records", "staffId"),
        ("personnel-info.training-experiences", "staffNum"),
    ):
        params: dict[str, object] = {key: staff_number}
        if endpoint.endswith("training-records"):
            params["page"] = 1
        verifier.call(
            "ieb",
            f"api.{endpoint}",
            lambda endpoint=endpoint, params=params: executor.execute(endpoint, params),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )


def verify_app(verifier: Any) -> None:
    from http_qualification_query.manager import RunManager
    from http_qualification_query.server import create_server

    try:
        with TemporaryDirectory(prefix="csn2api-real-personnel-") as directory:
            manager = RunManager(Path(directory))
            server = create_server(APP_ROOT, 0, manager)
            with serve_app(server, manager) as base_url:
                verify_frontend_route(base_url, "/api/run")
                post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["ieb"]})
                post_json(
                    base_url,
                    "/api/run",
                    {
                        "inputMode": "paste",
                        "pastedText": f"{verifier.input('iebStaffNumber')} {verifier.inputs.get('iebStaffName', '')}",
                    },
                )
                state = require_completed(wait_for_final(base_url))
        progress = state.get("progress", {})
        results = state.get("results", [])
        if progress.get("success") != 1 or not isinstance(results, list) or len(results) != 1:
            raise RuntimeError("前端人员查询未成功返回唯一结果")
        operation_count = results[0].get("operationCount", 0)
        verifier.record(
            "ieb",
            "app.personnel-info.all",
            "PASS",
            f"前端 /api/run 已接通，成功 1 条，运行资格 {operation_count} 条",
        )
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "app.personnel-info.all", error)
