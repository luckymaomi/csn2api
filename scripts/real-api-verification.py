#!/usr/bin/env python3
"""按真实页面正向链路验收 API 文档和独立 APP。

本入口只负责凭据段落解析、参数校验和调度；具体系统用例位于
``scripts/real_verification``，不会维护第二套生产请求实现。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from real_verification.common import (
    configure_import_paths,
    load_credential_sections,
    load_verification_inputs,
)
from real_verification.runner import CASE_SYSTEMS, RealVerifier


ROOT = Path(__file__).resolve().parents[1]
configure_import_paths()
CASE_NAMES = (
    "flight-stats",
    "personnel-info",
    "qualification-roster",
    "qualification-monitor",
    "lock-entry",
    "oa-read",
    "caac-pilot-export",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按真实页面正向链路验收 API 文档和独立 APP")
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=ROOT / "cookie.txt",
        help="Markdown Cookie 模板或现有 cookie.txt",
    )
    parser.add_argument(
        "--scope",
        choices=("api", "app", "both"),
        default="both",
        help="验收 API、APP 或两者",
    )
    parser.add_argument(
        "--system",
        choices=("all", "ieb", "oa", "caac"),
        default="all",
        help="只验收一个系统；默认验收 IEB、OA、CAAC",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="临时覆盖本地 Markdown 的验收参数；可重复填写",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=CASE_NAMES,
        default=[],
        help="只执行指定业务模块；可重复填写",
    )
    parser.add_argument("--allow-write", action="store_true", help="允许本轮明确授权的写操作")
    parser.add_argument(
        "--lock-confirmation",
        default="",
        help="必须与本地验收参数拼接出的员工号|类型|开始日期|结束日期|备注完全一致",
    )
    parser.add_argument("--oa-read-count", type=int, default=None, help="OA 已阅数量；本轮只能填写 1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.cookies_file.is_file():
        print(f"凭据文件不存在：{args.cookies_file}")
        return 2
    sections = load_credential_sections(args.cookies_file)
    inputs = load_verification_inputs(args.cookies_file)
    for assignment in args.set:
        key, separator, value = str(assignment).partition("=")
        if not separator or not key.strip() or not value.strip():
            print(f"验收参数覆盖格式无效：{assignment}")
            return 2
        inputs[key.strip()] = value.strip()
    selected_cases = set(args.case)
    case_systems = {CASE_SYSTEMS[name] for name in selected_cases}
    if args.system != "all" and any(system != args.system for system in case_systems):
        print("--case 与 --system 所属系统不一致")
        return 2
    required = case_systems or ({args.system} if args.system != "all" else {"ieb", "oa", "caac"})
    missing = sorted(system for system in required if not sections.get(system))
    if missing:
        print(f"Cookie 模板缺少系统段落：{', '.join(missing)}")
        return 2
    required_inputs: set[str] = set()
    if "ieb" in required and (not selected_cases or selected_cases & {"flight-stats", "personnel-info"}):
        required_inputs.add("iebStaffNumber")
    if "ieb" in required and (not selected_cases or "flight-stats" in selected_cases):
        required_inputs.update({"flightStartDate", "flightEndDate"})
    if "ieb" in required and (not selected_cases or "qualification-roster" in selected_cases):
        required_inputs.add("iebRosterQualification")
    if (
        "ieb" in required
        and args.scope in {"app", "both"}
        and (not selected_cases or "qualification-monitor" in selected_cases)
    ):
        required_inputs.add("iebMonitorQualification")
    lock_selected = not selected_cases or "lock-entry" in selected_cases
    if "ieb" in required and lock_selected and (args.scope in {"app", "both"} or args.lock_confirmation):
        required_inputs.update(
            {"lockStaffNumber", "lockType", "lockStartDate", "lockEndDate", "lockRemark"}
        )
    if "caac" in required and (not selected_cases or "caac-pilot-export" in selected_cases):
        required_inputs.add("caacPilotName")
    missing_inputs = sorted(name for name in required_inputs if not inputs.get(name))
    if missing_inputs:
        print(f"本地验收参数缺少：{', '.join(missing_inputs)}")
        return 2
    if args.oa_read_count not in (None, 1):
        print("本轮 OA 已阅授权上限为 1 条")
        return 2
    if args.oa_read_count is not None and not args.allow_write:
        print("填写 --oa-read-count 时必须同时填写 --allow-write")
        return 2
    if args.lock_confirmation and not args.allow_write:
        print("填写 --lock-confirmation 时必须同时填写 --allow-write")
        return 2
    expected_lock = "|".join(
        inputs.get(name, "")
        for name in ("lockStaffNumber", "lockType", "lockStartDate", "lockEndDate", "lockRemark")
    )
    if args.allow_write and args.lock_confirmation and args.lock_confirmation != expected_lock:
        print("锁班确认串不匹配当前授权对象、日期、类型或备注")
        return 2
    verifier = RealVerifier(
        sections,
        inputs,
        args.scope,
        args.system,
        selected_cases,
        args.allow_write,
        args.lock_confirmation,
        args.oa_read_count,
    )
    return verifier.run()


if __name__ == "__main__":
    raise SystemExit(main())
