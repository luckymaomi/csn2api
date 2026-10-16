"""IEB 飞行门户真实验收编排；业务 Case 位于 ``real_verification.ieb``。"""

from __future__ import annotations

import sys
from typing import Any

from .common import API_DOCS_ROOT, ROOT
from .ieb import (
    flight_detail,
    flight_stats,
    flight_history,
    lock_entry,
    personnel_info,
    qualification_monitor,
    qualification_roster,
)


APP_ROOTS = [
    ROOT / "public/tool/app/http-flight-history-helper",
    ROOT / "public/tool/app/http-flight-stats-helper",
    ROOT / "public/tool/app/http-flight-detail-helper",
    ROOT / "public/tool/app/http-qualification-query-helper",
    ROOT / "public/tool/app/http-qualification-roster-helper",
    ROOT / "public/tool/app/http-qualification-monitor-helper",
    ROOT / "public/tool/app/http-lock-entry-helper",
]
CASES = (
    ("flight-history", flight_history),
    ("flight-detail", flight_detail),
    ("flight-stats", flight_stats),
    ("personnel-info", personnel_info),
    ("qualification-roster", qualification_roster),
    ("qualification-monitor", qualification_monitor),
    ("lock-entry", lock_entry),
)


def verify_api_ieb(verifier: Any) -> None:
    from api_docs.catalog import ApiCatalog
    from api_docs.executor import ApiExecutor

    executor = ApiExecutor(ApiCatalog(API_DOCS_ROOT / "catalog"))
    try:
        try:
            summary = executor.load_credentials(verifier.credentials["ieb"], "flight-portal")
        except Exception as error:  # noqa: BLE001 - 会话失效时由运行器停止 IEB
            verifier.fail("ieb", "api.session", error)
            return
        verifier.record("ieb", "api.session", "PASS", f"Cookie 字段 {summary.get('cookieCount', 0)}，当前登录身份已返回")
        for name, case in CASES:
            if "ieb" in verifier.halted:
                break
            if verifier.selected_case(name):
                case.verify_api(verifier, executor)
    finally:
        executor.close()


def verify_app_ieb(verifier: Any) -> None:
    if "ieb" in verifier.halted:
        verifier.record("ieb", "app", "STOPPED", "API 真实验收已确认 IEB 会话失效，未继续请求")
        return
    for root in APP_ROOTS:
        sys.path.insert(0, str(root))
    try:
        for name, case in CASES:
            if "ieb" in verifier.halted:
                break
            if verifier.selected_case(name):
                case.verify_app(verifier)
    finally:
        for root in APP_ROOTS:
            try:
                sys.path.remove(str(root))
            except ValueError:
                pass


__all__ = ["verify_api_ieb", "verify_app_ieb"]
