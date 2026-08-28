from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


def discover_server_package(app_root: Path) -> str:
    packages = sorted(
        child.name
        for child in app_root.iterdir()
        if child.is_dir()
        and (child / "__init__.py").is_file()
        and (child / "server.py").is_file()
    )
    if len(packages) != 1:
        raise RuntimeError(f"{app_root.name} 必须包含一个 Python server 包，实际 {len(packages)} 个")
    return packages[0]


def create_application_server(app_root: Path, port: int = 0) -> Any:
    root = app_root.resolve()
    package = discover_server_package(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    module = importlib.import_module(f"{package}.server")
    return module.create_server(root, port)


def close_application_server(server: Any, *, shutdown: bool) -> None:
    if shutdown:
        server.shutdown()
    manager = getattr(server, "run_manager", None)
    executor = getattr(server, "executor", None)
    target = manager or executor
    close = getattr(target, "shutdown", None) or getattr(target, "close", None)
    if callable(close):
        close()
    server.server_close()
