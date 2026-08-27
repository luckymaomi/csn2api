"""CAAC 云执照 API 文档与独立 APP 的真实验收用例。"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from .common import API_DOCS_ROOT, ROOT, result_summary


def verify_caac(verifier: Any, *, api: bool) -> None:
    if api:
        _verify_api(verifier)
    else:
        _verify_app(verifier)


def _verify_api(verifier: Any) -> None:
    from api_docs.catalog import ApiCatalog
    from api_docs.executor import ApiExecutor

    executor = ApiExecutor(ApiCatalog(API_DOCS_ROOT / "catalog"))
    try:
        try:
            summary = executor.load_credentials(verifier.credentials["caac"], "caac-fsop")
        except Exception as error:  # noqa: BLE001
            verifier.fail("caac", "api.session", error)
            return
        verifier.record("caac", "api.session", "PASS", f"Cookie 字段 {summary.get('cookieCount', 0)}，列表会话验证已返回")
        verifier.call(
            "caac",
            "api.caac-pilot-export.pilot-list",
            lambda: executor.execute("caac-pilot-export.pilot-list", {"page": 1, "rows": 10}),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )
        verifier.call(
            "caac",
            "api.caac-pilot-export.pilot-detail",
            lambda: executor.execute("caac-pilot-export.pilot-detail", {"pilotname": verifier.input("caacPilotName")}),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )
    finally:
        executor.close()


def _verify_app(verifier: Any) -> None:
    root = ROOT / "public/tool/app/http-caac-pilot-export-helper"
    sys.path.insert(0, str(root))
    try:
        from caac_pilot_export.manager import RunManager
        from caac_pilot_export.server import create_server

        try:
            content = _selected_workbook(verifier.input("caacPilotName"))
            with TemporaryDirectory(prefix="csn2api-real-caac-") as directory:
                manager = RunManager(Path(directory))
                server = create_server(root, 0, manager)
                with serve_app(server, manager) as base_url:
                    verify_frontend_route(base_url, "/api/run")
                    session = post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["caac"]})
                    post_json(
                        base_url,
                        "/api/run",
                        {
                            "mode": "selected",
                            "excelName": "real-verification.xlsx",
                            "excelBase64": base64.b64encode(content).decode("ascii"),
                        },
                    )
                    state = require_completed(wait_for_final(base_url, timeout_seconds=300))
            progress = state.get("progress", {})
            verifier.record("caac", "app.caac-pilot-export.pilot-list", "PASS", f"前端 /api/run 已接通，服务端列表总数 {session.get('totalFromServer', 0)}")
            verifier.record("caac", "app.caac-pilot-export.pilot-detail", "PASS", f"按姓名唯一归属并抓取详情，成功 {progress.get('success', 0)} 条")
        except Exception as error:  # noqa: BLE001
            verifier.fail("caac", "app.caac-pilot-export", error)
    finally:
        sys.path.remove(str(root))


def _selected_workbook(pilot_name: str) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.append(["姓名", "档案号"])
        sheet.append([pilot_name, ""])
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
    finally:
        workbook.close()


__all__ = ["verify_caac"]
