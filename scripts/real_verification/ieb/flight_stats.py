from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-flight-stats-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    staff_number = verifier.input("iebStaffNumber")
    start_date = verifier.input("flightStartDate")
    end_date = verifier.input("flightEndDate")
    verifier.call(
        "ieb",
        "api.flight-stats.query",
        lambda: executor.execute(
            "flight-stats.query",
            {"staffNum": staff_number, "startStr": start_date, "endStr": end_date},
        ),
        detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
    )


def verify_app(verifier: Any) -> None:
    from http_flight_stats.manager import RunManager
    from http_flight_stats.server import create_server

    try:
        staff_number = verifier.input("iebStaffNumber")
        staff_name = verifier.inputs.get("iebStaffName", "")
        start_date = date.fromisoformat(verifier.input("flightStartDate"))
        end_date = date.fromisoformat(verifier.input("flightEndDate"))
        with TemporaryDirectory(prefix="csn2api-real-flight-") as directory:
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
                        "pastedText": f"{staff_number} {staff_name} {start_date.isoformat()} {end_date.isoformat()}",
                        "scope": "all",
                    },
                )
                state = require_completed(wait_for_final(base_url))
        progress = state.get("progress", {})
        verifier.record(
            "ieb",
            "app.flight-stats.query",
            "PASS",
            f"前端 /api/run 已接通，成功 {progress.get('success', 0)} 条",
        )
    except Exception as error:  # noqa: BLE001 - 真实验收记录单项失败
        verifier.fail("ieb", "app.flight-stats.query", error)
