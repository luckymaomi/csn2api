from __future__ import annotations

import sys
import threading
import unittest
import urllib.request
from pathlib import Path
from typing import Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app"
WORKBENCH_ROOTS = {
    name: APP_ROOT / name
    for name in (
        "http-flight-stats-helper",
        "http-lock-entry-helper",
        "http-oa-read-helper",
        "http-qualification-query-helper",
        "http-qualification-monitor-helper",
        "http-soc-positioning-helper",
    )
}
for workbench_root in WORKBENCH_ROOTS.values():
    if str(workbench_root) not in sys.path:
        sys.path.insert(0, str(workbench_root))

from http_flight_stats.server import create_server as create_flight_stats_server
from http_lock_entry.server import create_server as create_lock_entry_server
from http_oa_read.server import create_server as create_oa_read_server
from http_qualification_monitor.server import create_server as create_qualification_monitor_server
from http_qualification_query.server import create_server as create_qualification_query_server
from soc_positioning.server import create_server as create_soc_server


ServerFactory = Callable[[], object]


class HttpWorkbenchAssetTests(unittest.TestCase):
    def test_each_workbench_serves_the_keepalive_module(self) -> None:
        manager = object()
        factories: dict[str, ServerFactory] = {
            "http-flight-stats-helper": lambda: create_flight_stats_server(
                WORKBENCH_ROOTS["http-flight-stats-helper"], 0, manager  # type: ignore[arg-type]
            ),
            "http-lock-entry-helper": lambda: create_lock_entry_server(
                WORKBENCH_ROOTS["http-lock-entry-helper"], "original", 0, manager  # type: ignore[arg-type]
            ),
            "http-oa-read-helper": lambda: create_oa_read_server(
                WORKBENCH_ROOTS["http-oa-read-helper"], 0, manager
            ),
            "http-qualification-query-helper": lambda: create_qualification_query_server(
                WORKBENCH_ROOTS["http-qualification-query-helper"], 0, manager  # type: ignore[arg-type]
            ),
            "http-qualification-monitor-helper": lambda: create_qualification_monitor_server(
                WORKBENCH_ROOTS["http-qualification-monitor-helper"], 0, manager  # type: ignore[arg-type]
            ),
            "http-soc-positioning-helper": lambda: create_soc_server(
                WORKBENCH_ROOTS["http-soc-positioning-helper"], 0, manager  # type: ignore[arg-type]
            ),
        }

        for name, factory in factories.items():
            with self.subTest(workbench=name):
                server = factory()
                thread = threading.Thread(target=server.serve_forever, daemon=True)  # type: ignore[attr-defined]
                thread.start()
                host, port = server.server_address  # type: ignore[attr-defined]
                try:
                    with urllib.request.urlopen(
                        f"http://{host}:{port}/session_keepalive.mjs", timeout=5
                    ) as response:
                        body = response.read().decode("utf-8")
                        self.assertEqual(response.status, 200)
                        self.assertIn("javascript", response.headers.get_content_type())
                        self.assertIn("export function renderKeepAlive", body)
                finally:
                    server.shutdown()  # type: ignore[attr-defined]
                    thread.join(timeout=5)
                    server.server_close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
