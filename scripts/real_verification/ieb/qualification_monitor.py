from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-qualification-monitor-helper"


def _endpoint_code(endpoint: dict[str, object]) -> str:
    protocol_code = str(endpoint.get("protocolCode") or "").strip()
    if protocol_code:
        return protocol_code
    return next((
        str(parameter.get("default") or "").strip()
        for parameter in endpoint.get("parameters", [])
        if isinstance(parameter, dict)
        and parameter.get("name") == "qualType"
        and parameter.get("fixed") is True
    ), "")


def _api_detail(value: object) -> str:
    if not isinstance(value, dict):
        return str(value)
    final_path = str(value.get("finalUrl") or "").split("?", 1)[0]
    return f"HTTP {value.get('status')}，{result_summary(value)}，路径 {final_path}"


def verify_api(verifier: Any, executor: Any) -> None:
    monitor = executor.catalog.modules["qualification-monitor"]
    endpoints = [endpoint for endpoint in monitor.get("endpoints", []) if isinstance(endpoint, dict)]
    protocol = executor.flight_portal.monitor
    if protocol is None:
        verifier.fail("ieb", "api.qualification-monitor.metadata", RuntimeError("资质监控共享 core 未初始化"))
        return
    try:
        _response, groups = protocol.request_classification()
        dynamic_items = [item for group in groups for item in group.items]
        by_code = {_endpoint_code(endpoint): endpoint for endpoint in endpoints}
        dynamic_codes = [item.code for item in dynamic_items]
        if not all(dynamic_codes) or set(dynamic_codes) != set(by_code):
            raise RuntimeError("门户动态资质与 API catalog 不一致")
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "api.qualification-monitor.metadata", error)
        return
    verifier.record(
        "ieb",
        "api.qualification-monitor.metadata",
        "PASS",
        f"动态分类 {len(groups)} 组、{len(dynamic_items)} 项，与 API catalog 一致",
    )
    totals: dict[str, int] = {}
    for item in dynamic_items:
        endpoint = by_code[item.code]
        endpoint_id = str(endpoint.get("id", ""))
        value = verifier.call(
            "ieb",
            f"api.qualification-monitor.{endpoint_id}",
            lambda endpoint_id=endpoint_id: executor.execute(
                f"qualification-monitor.{endpoint_id}", {"pageNum": 1, "pageSize": 20}
            ),
            detail=_api_detail,
        )
        if isinstance(value, dict):
            summary = value.get("data", {}).get("summary", {}) if isinstance(value.get("data"), dict) else {}
            if isinstance(summary, dict) and isinstance(summary.get("total"), int):
                totals[item.code] = summary["total"]
    if len(totals) == len(dynamic_items):
        empty = [code for code, total in totals.items() if total == 0]
        verifier.record(
            "ieb",
            "api.qualification-monitor.totals",
            "PASS",
            f"有数据 {len(totals) - len(empty)} 项，空数据 {len(empty)} 项：{', '.join(empty) if empty else '无'}",
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
