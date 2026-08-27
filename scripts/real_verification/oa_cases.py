"""OA API 文档与独立 APP 的真实验收用例。"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from .common import API_DOCS_ROOT, ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-oa-read-helper"


def verify_api_oa(verifier: Any) -> None:
    from api_docs.catalog import ApiCatalog
    from api_docs.executor import ApiExecutor

    executor = ApiExecutor(ApiCatalog(API_DOCS_ROOT / "catalog"))
    try:
        try:
            summary = executor.load_credentials(verifier.credentials["oa"], "oa")
        except Exception as error:  # noqa: BLE001
            verifier.fail("oa", "api.session", error)
            return
        verifier.record("oa", "api.session", "PASS", f"Cookie 字段 {summary.get('cookieCount', 0)}，当前登录身份已返回")
        verifier.call(
            "oa",
            "api.oa-read.count",
            lambda: executor.execute("oa-read.count", {}),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )
        if not verifier.allow_write or verifier.oa_read_count is None:
            verifier.record("oa", "api.oa-read.read", "SKIP", "未提供本轮 OA 已阅写操作显式确认")
        elif not verifier.claim_write("oa"):
            verifier.record("oa", "api.oa-read.read", "SKIP", "本轮 OA 已阅写额度已由其他入口消耗", write=True)
        else:
            def read_one() -> object:
                value = executor.execute("oa-read.read", {"count": verifier.oa_read_count})
                data = value.get("data") if isinstance(value, dict) else None
                result = data.get("summary") if isinstance(data, dict) else None
                if (
                    not isinstance(result, dict)
                    or int(result.get("target") or 0) != 1
                    or int(result.get("success") or 0) != 1
                    or int(result.get("failed") or 0) != 0
                ):
                    raise RuntimeError("OA 已阅响应没有通过单条业务成功契约")
                return value

            verifier.call(
                "oa",
                "api.oa-read.read",
                read_one,
                write=True,
                detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
            )
    finally:
        executor.close()


def verify_app_oa(verifier: Any) -> None:
    sys.path.insert(0, str(APP_ROOT))
    try:
        from http_oa_read.manager import RunManager
        from http_oa_read.server import create_server

        try:
            with TemporaryDirectory(prefix="csn2api-real-oa-") as directory:
                manager = RunManager(Path(directory))
                server = create_server(APP_ROOT, 0, manager)
                with serve_app(server, manager) as base_url:
                    verify_frontend_route(base_url, "/api/scan")
                    session = post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["oa"]})
                    state = post_json(base_url, "/api/scan", {})
                    scan = state.get("scan", {})
                    if not isinstance(scan, dict) or not scan.get("current"):
                        raise RuntimeError("APP OA 扫描路由没有返回当前有效扫描结果")
                    should_write = verifier.allow_write and verifier.oa_read_count is not None and verifier.claim_write("oa")
                    if should_write:
                        verify_frontend_route(base_url, "/api/run")
                        post_json(base_url, "/api/run", {"maxCount": verifier.oa_read_count, "runMode": "finite"})
                        final = require_completed(wait_for_final(base_url))
            verifier.record(
                "oa",
                "app.oa-read.scan",
                "PASS",
                f"前端 /api/scan 已接通，待办 {scan.get('total', 0)}，可已阅 {scan.get('eligibleCount', 0)}，跳过 {scan.get('skippedCount', 0)}",
            )
            if not verifier.allow_write or verifier.oa_read_count is None:
                return
            if not should_write:
                verifier.record("oa", "app.oa-read.have-read", "SKIP", "本轮 OA 已阅写额度已由 API 入口消耗", write=True)
                return
            progress = final.get("progress", {})
            verifier.record("oa", "app.oa-read.have-read", "PASS", f"前端 /api/run 已接通，成功 {progress.get('success', 0)} 条", write=True)
        except Exception as error:  # noqa: BLE001
            verifier.fail("oa", "app.oa-read", error, write=verifier.oa_read_count is not None)
    finally:
        sys.path.remove(str(APP_ROOT))


__all__ = ["verify_api_oa", "verify_app_oa"]
