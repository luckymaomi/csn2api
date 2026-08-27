from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-qualification-monitor-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    monitor = executor.catalog.modules["qualification-monitor"]
    for endpoint in monitor.get("endpoints", []):
        if not isinstance(endpoint, dict):
            continue
        endpoint_id = str(endpoint.get("id", ""))
        verifier.call(
            "ieb",
            f"api.qualification-monitor.{endpoint_id}",
            lambda endpoint_id=endpoint_id: executor.execute(
                f"qualification-monitor.{endpoint_id}", {"pageNum": 1, "pageSize": 20}
            ),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )


def verify_app(verifier: Any) -> None:
    from http_qualification_monitor.manager import RunManager
    from http_qualification_monitor.server import create_server

    try:
        qualification = verifier.input("iebMonitorQualification")
        with TemporaryDirectory(prefix="csn2api-real-monitor-") as directory:
            manager = RunManager(Path(directory))
            server = create_server(APP_ROOT, 0, manager)
            with serve_app(server, manager) as base_url:
                verify_frontend_route(base_url, "/api/export/one")
                session = post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["ieb"]})
                groups = session.get("groups", [])
                items = [item for group in groups if isinstance(group, dict) for item in group.get("items", []) if isinstance(item, dict)]
                if not any(str(item.get("code") or "") == qualification for item in items):
                    raise RuntimeError("APP 动态资质中不存在本轮验收代码")
                post_json(base_url, "/api/export/one", {"qualType": qualification})
                state = require_completed(wait_for_final(base_url), minimum_success=1)
        verifier.record(
            "ieb",
            "app.qualification-monitor.metadata",
            "PASS",
            f"动态资质 {len(items)}，本轮资质代码存在",
        )
        progress = state.get("progress", {})
        verifier.record("ieb", f"app.qualification-monitor.{qualification}", "PASS", f"前端 /api/export/one 已接通，成功 {progress.get('success', 0)} 项")
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "app.qualification-monitor.metadata", error)
