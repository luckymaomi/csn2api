from __future__ import annotations

import importlib
import inspect
import sys
import threading
import unittest
import urllib.request
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app"


@dataclass(frozen=True)
class Workbench:
    root: Path
    package_name: str


def discover_workbenches() -> list[Workbench]:
    workbenches: list[Workbench] = []
    for root in sorted(APP_ROOT.glob("http-*-helper")):
        if not (root / "web" / "index.html").is_file():
            continue
        packages = [
            child
            for child in root.iterdir()
            if child.is_dir() and (child / "__init__.py").is_file() and (child / "server.py").is_file()
        ]
        if len(packages) != 1:
            raise AssertionError(f"{root.name} 应包含一个可独立运行的 Python server 包，实际 {len(packages)} 个")
        workbenches.append(Workbench(root, packages[0].name))
    return workbenches


WORKBENCHES = discover_workbenches()
for workbench in WORKBENCHES:
    if str(workbench.root) not in sys.path:
        sys.path.insert(0, str(workbench.root))


def create_workbench_server(workbench: Workbench) -> object:
    module = importlib.import_module(f"{workbench.package_name}.server")
    factory = module.create_server
    parameters = inspect.signature(factory).parameters
    manager = object()
    if "mode" in parameters:
        return factory(workbench.root, "original", 0, manager)
    return factory(workbench.root, 0, manager)


class HttpWorkbenchAssetTests(unittest.TestCase):
    def test_discovers_every_http_workbench(self) -> None:
        expected = [
            root
            for root in APP_ROOT.glob("http-*-helper")
            if (root / "web" / "index.html").is_file()
        ]
        self.assertGreater(len(WORKBENCHES), 0)
        self.assertEqual(len(WORKBENCHES), len(expected))

    def test_each_workbench_serves_the_standard_keepalive_module(self) -> None:
        canonical = (APP_ROOT / "_shared" / "session_keepalive.mjs").read_text(encoding="utf-8")
        for workbench in WORKBENCHES:
            with self.subTest(workbench=workbench.root.name):
                server = create_workbench_server(workbench)
                thread = threading.Thread(target=server.serve_forever, daemon=True)  # type: ignore[attr-defined]
                thread.start()
                host, port = server.server_address  # type: ignore[attr-defined]
                try:
                    with urllib.request.urlopen(f"http://{host}:{port}/session_keepalive.mjs", timeout=5) as response:
                        body = response.read().decode("utf-8")
                        self.assertEqual(response.status, 200)
                        self.assertIn("javascript", response.headers.get_content_type())
                        self.assertEqual(body.replace("\r\n", "\n"), canonical)
                finally:
                    server.shutdown()  # type: ignore[attr-defined]
                    thread.join(timeout=5)
                    server.server_close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
