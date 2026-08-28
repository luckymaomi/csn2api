from __future__ import annotations

import json

from .backend import request_backend
from .supervisor import RuntimeSupervisor


class CredentialRuntime:
    def __init__(self, supervisor: RuntimeSupervisor) -> None:
        self.supervisor = supervisor

    def request(self, method: str, body: bytes | None) -> tuple[int, dict[str, object]]:
        status, _headers, content = request_backend(
            self.supervisor,
            "api-docs",
            method,
            "/api/credentials",
            body,
            {"Content-Type": "application/json"},
        )
        result = json.loads(content.decode("utf-8"))
        if status >= 400 or method != "POST":
            return status, result

        failed = result.get("failed")
        failed_items = list(failed) if isinstance(failed, list) else []
        result["failed"] = failed_items
        bundle = result.get("bundle")
        systems = bundle.get("systems") if isinstance(bundle, dict) else []
        credentials = {
            str(item.get("systemId", "")): str(item.get("credentials", ""))
            for item in systems
            if isinstance(item, dict)
        }
        for target in self.supervisor.targets.values():
            value = credentials.get(target.system_id)
            if not target.system_id or not value:
                continue
            try:
                target_status, _target_headers, target_content = request_backend(
                    self.supervisor,
                    target.entry,
                    "POST",
                    "/api/session/verify",
                    json.dumps({"credentials": value}, ensure_ascii=False).encode("utf-8"),
                    {"Content-Type": "application/json"},
                )
                if target_status >= 400:
                    target_result = json.loads(target_content.decode("utf-8"))
                    raise ValueError(str(target_result.get("error", "验证失败")))
            except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                failed_items.append({"entry": target.entry, "error": str(error)})
        return status, result


__all__ = ["CredentialRuntime"]
