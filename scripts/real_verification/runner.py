from __future__ import annotations

from typing import Any, Callable

from .common import CaseResult, describe, is_session_failure, redact


CASE_SYSTEMS = {
    "flight-stats": "ieb",
    "personnel-info": "ieb",
    "qualification-roster": "ieb",
    "qualification-monitor": "ieb",
    "lock-entry": "ieb",
    "oa-read": "oa",
    "caac-pilot-export": "caac",
}


class RealVerifier:
    def __init__(
        self,
        credentials: dict[str, str],
        inputs: dict[str, str],
        scope: str,
        system: str,
        cases: set[str],
        allow_write: bool,
        lock_confirmation: str,
        oa_read_count: int | None,
    ) -> None:
        self.credentials = credentials
        self.inputs = inputs
        self.scope = scope
        self.system = system
        self.cases = cases
        self.allow_write = allow_write
        self.lock_confirmation = lock_confirmation
        self.oa_read_count = oa_read_count
        self.results: list[CaseResult] = []
        self.halted: set[str] = set()
        self.write_consumed: set[str] = set()

    def input(self, name: str) -> str:
        value = self.inputs.get(name, "").strip()
        if not value:
            raise ValueError(f"本地验收参数缺少 {name}")
        return value

    def selected(self, system: str) -> bool:
        system_selected = self.system == "all" or self.system == system
        case_selected = not self.cases or any(CASE_SYSTEMS.get(name) == system for name in self.cases)
        return system_selected and case_selected

    def selected_case(self, name: str) -> bool:
        return not self.cases or name in self.cases

    def claim_write(self, system: str) -> bool:
        """为同一系统的本轮真实写操作占用唯一额度。"""
        if system in self.write_consumed:
            return False
        self.write_consumed.add(system)
        return True

    def record(self, system: str, entry: str, status: str, detail: str, *, write: bool = False) -> None:
        result = CaseResult(system, entry, status, redact(detail), write)
        self.results.append(result)
        print(f"[{system}] {entry}: {status} - {result.detail}")

    def fail(self, system: str, entry: str, error: BaseException, *, write: bool = False) -> None:
        if is_session_failure(error):
            self.halted.add(system)
            self.record(system, entry, "SESSION_EXPIRED", str(error), write=write)
        else:
            self.record(system, entry, "FAIL", str(error), write=write)

    def call(self, system: str, entry: str, operation: Callable[[], object], *, write: bool = False, detail: Callable[[object], str] | None = None) -> object | None:
        if system in self.halted:
            self.record(system, entry, "STOPPED", "该系统会话已失效，未继续请求", write=write)
            return None
        try:
            value = operation()
        except Exception as error:  # noqa: BLE001 - 真实验收需要记录单项失败并继续
            self.fail(system, entry, error, write=write)
            return None
        self.record(system, entry, "PASS", detail(value) if detail else describe(value), write=write)
        return value

    def run(self) -> int:
        from .caac_cases import verify_caac
        from .ieb_cases import verify_app_ieb, verify_api_ieb
        from .oa_cases import verify_app_oa, verify_api_oa

        if self.scope in {"api", "both"}:
            if self.selected("ieb"):
                verify_api_ieb(self)
            if self.selected("oa") and self.selected_case("oa-read"):
                verify_api_oa(self)
            if self.selected("caac") and self.selected_case("caac-pilot-export"):
                verify_caac(self, api=True)
        if self.scope in {"app", "both"}:
            if self.selected("ieb"):
                verify_app_ieb(self)
            if self.selected("oa") and self.selected_case("oa-read"):
                verify_app_oa(self)
            if self.selected("caac") and self.selected_case("caac-pilot-export"):
                verify_caac(self, api=False)
        passed = sum(item.status == "PASS" for item in self.results)
        failed = sum(item.status == "FAIL" or item.status.endswith("FAIL") for item in self.results)
        stopped = sum(item.status == "SESSION_EXPIRED" for item in self.results)
        print(f"\n真实验收汇总：PASS={passed}，FAIL={failed}，SESSION_EXPIRED={stopped}，总 Case={len(self.results)}")
        return 1 if failed or stopped else 0
