from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .application import close_application_server, create_application_server


IDLE_PHASES = {
    "waiting_credentials",
    "credentials_ready",
    "data_checked",
    "scan_ready",
    "ready",
    "completed",
    "failed",
    "session_expired",
    "terminated",
    "stopped",
    "partial_failure",
}


@dataclass
class RuntimeTarget:
    entry: str
    name: str
    app_root: Path
    system_id: str = ""
    server: Any | None = None
    thread: threading.Thread | None = None


class RuntimeSupervisor:
    def __init__(self, targets: list[RuntimeTarget]) -> None:
        self.targets = {target.entry: target for target in targets}
        self.lock = threading.RLock()

    def start_all(self) -> None:
        with self.lock:
            try:
                for target in self.targets.values():
                    self._start(target)
            except Exception:
                for target in reversed(list(self.targets.values())):
                    self._stop(target)
                raise

    def stop_all(self) -> None:
        with self.lock:
            for target in reversed(list(self.targets.values())):
                self._stop(target)

    def restart_all(self) -> None:
        with self.lock:
            self.stop_all()
            self.start_all()

    def port(self, entry: str) -> int:
        target = self.targets.get(entry)
        if target is None or target.server is None:
            raise KeyError(entry)
        return int(target.server.server_address[1])

    def busy(self) -> bool:
        with self.lock:
            for target in self.targets.values():
                server = target.server
                if server is None:
                    continue
                tasks = getattr(server, "execution_tasks", None)
                if tasks is not None and bool(getattr(tasks, "active_systems", {})):
                    return True
                manager = getattr(server, "run_manager", None)
                snapshot = getattr(manager, "snapshot", None)
                if callable(snapshot):
                    phase = str(snapshot().get("phase", ""))
                    if phase and phase not in IDLE_PHASES:
                        return True
            return False

    @staticmethod
    def _start(target: RuntimeTarget) -> None:
        server = create_application_server(target.app_root, 0)
        thread = threading.Thread(
            target=server.serve_forever,
            name=f"csn2api-{target.entry}",
            daemon=True,
        )
        thread.start()
        target.server = server
        target.thread = thread

    @staticmethod
    def _stop(target: RuntimeTarget) -> None:
        if target.server is None:
            return
        close_application_server(target.server, shutdown=True)
        if target.thread is not None:
            target.thread.join(timeout=5)
        target.server = None
        target.thread = None


__all__ = ["RuntimeSupervisor", "RuntimeTarget"]
