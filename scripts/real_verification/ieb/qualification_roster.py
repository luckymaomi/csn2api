from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ..app_http import post_json, require_completed, serve_app, verify_frontend_route, wait_for_final
from ..common import ROOT, result_summary


APP_ROOT = ROOT / "public/tool/app/http-qualification-roster-helper"


def verify_api(verifier: Any, executor: Any) -> None:
    filters = {
        "fleetCdToArray": ["777"],
        "activeStatusArray": ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"],
        "operQualArray": verifier.input("iebRosterQualification"),
    }
    for endpoint, params in (
        ("qualification-roster.filter-page", {}),
        ("qualification-roster.operating-qualifications", {}),
        ("qualification-roster.query", filters),
        ("qualification-roster.native-export", filters),
    ):
        verifier.call(
            "ieb",
            f"api.{endpoint}",
            lambda endpoint=endpoint, params=params: executor.execute(endpoint, params),
            detail=lambda value: f"HTTP {value.get('status')}，{result_summary(value)}" if isinstance(value, dict) else str(value),
        )


def verify_app(verifier: Any) -> None:
    from http_qualification_roster.manager import RunManager
    from http_qualification_roster.server import create_server

    try:
        qualification = verifier.inputs.get("iebRosterQualification", "").strip()
        if not qualification:
            raise ValueError("本地验收参数缺少 iebRosterQualification")
        with TemporaryDirectory(prefix="csn2api-real-roster-") as directory:
            manager = RunManager(Path(directory))
            server = create_server(APP_ROOT, 0, manager)
            with serve_app(server, manager) as base_url:
                verify_frontend_route(base_url, "/api/run")
                session = post_json(base_url, "/api/session/verify", {"credentials": verifier.credentials["ieb"]})
                post_json(
                    base_url,
                    "/api/run",
                    {
                        "filters": {
                            "fleetCdToArray": ["777"],
                            "activeStatusArray": ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"],
                        },
                        "qualificationCodes": [qualification],
                    },
                )
                state = require_completed(wait_for_final(base_url))
        progress = state.get("progress", {})
        verifier.record("ieb", "app.qualification-roster.metadata", "PASS", f"动态筛选字段 {len(session.get('filterFields', []))}，动态资格 {len(session.get('qualifications', []))}")
        verifier.record("ieb", "app.qualification-roster.query", "PASS", f"前端 /api/run 已接通，关系 {progress.get('relationships', 0)} 条")
        verifier.record("ieb", "app.qualification-roster.native-export", "PASS", "真实名册结果已写入临时 Excel 并在验收后清理")
    except Exception as error:  # noqa: BLE001
        verifier.fail("ieb", "app.qualification-roster", error)
