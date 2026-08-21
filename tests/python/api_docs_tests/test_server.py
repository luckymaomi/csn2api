from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request

from .common import APP_ROOT, CATALOG_ROOT
from api_docs.catalog import ApiCatalog
from api_docs.server import create_server


class StubExecutor:
    def __init__(self) -> None:
        self.catalog = ApiCatalog(CATALOG_ROOT)
        self.ready = {"flight-portal": False, "oa": False}
        self.calls: list[tuple[object, ...]] = []
        self.progress_started = threading.Event()
        self.progress_release = threading.Event()

    def session_status(self, system_id="flight-portal") -> dict[str, object]:
        ready = self.ready[system_id]
        names = ["JSESSIONID", "iebJSid"] if system_id == "flight-portal" else ["SESSION", "ROUTE-SESSION"]
        return {"ready": ready, "cookieNames": names if ready else [], "cookieCount": 2 if ready else 0}

    def all_session_statuses(self) -> dict[str, dict[str, object]]:
        return {system_id: self.session_status(system_id) for system_id in self.ready}

    def load_credentials(self, source: str, system_id="flight-portal") -> dict[str, object]:
        self.calls.append(("session", system_id, bool(source)))
        self.ready[system_id] = True
        credentials = (
            "JSESSIONID=session-value; iebJSid=browser-value"
            if system_id == "flight-portal"
            else "SESSION=oa-value; ROUTE-SESSION=route-value"
        )
        return {
            **self.session_status(system_id),
            "credentials": credentials,
        }

    def clear_credentials(self, system_id=None) -> None:
        targets = list(self.ready) if system_id is None else [system_id]
        for target in targets:
            self.ready[target] = False

    def load_options(self, source: str) -> list[dict[str, str]]:
        self.calls.append(("options", source))
        return [{"value": "TEST", "label": "测试类型"}]

    def execute(self, endpoint_id: str, parameters: dict[str, object], progress_callback=None) -> dict[str, object]:
        self.calls.append(("execute", endpoint_id, parameters))
        if endpoint_id == "oa-read.read" and progress_callback is not None:
            progress_callback(self._execution_result([{"title": "第一条", "status": "成功"}]))
            self.progress_started.set()
            self.progress_release.wait(timeout=2)
            return self._execution_result([
                {"title": "第一条", "status": "成功"},
                {"title": "第二条", "status": "成功"},
            ])
        return self._execution_result([])

    @staticmethod
    def _execution_result(rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "status": 200,
            "body": "ok",
            "headers": {},
            "elapsedMilliseconds": 1,
            "data": {
                "tables": [{"id": "results", "title": "结果", "columns": ["title", "status"], "rows": rows}],
                "summary": {"success": len(rows)},
            },
        }


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = StubExecutor()
        self.server = create_server(APP_ROOT, 0, self.executor)  # type: ignore[arg-type]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, path: str, method: str = "GET", payload: object | None = None) -> dict[str, object]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_loopback_routes_share_catalog_and_manage_independent_sessions(self) -> None:
        health = self.request("/api/health")
        self.assertTrue(health["available"])
        catalog = self.request("/api/catalog")
        self.assertEqual(
            [module["id"] for module in catalog["modules"]],
            ["flight-stats", "lock-entry", "personnel-info", "oa-read"],
        )
        session = self.request(
            "/api/session",
            "POST",
            {"systemId": "flight-portal", "credentials": "secret-cookie-text"},
        )
        self.assertTrue(session["ready"])
        self.assertNotIn("secret-cookie-text", json.dumps(session))
        self.assertEqual(session["credentials"], "JSESSIONID=session-value; iebJSid=browser-value")
        oa_session = self.request(
            "/api/session",
            "POST",
            {"systemId": "oa", "credentials": "oa-cookie-text"},
        )
        self.assertTrue(oa_session["ready"])
        self.assertEqual(oa_session["credentials"], "SESSION=oa-value; ROUTE-SESSION=route-value")
        active_health = self.request("/api/health")
        self.assertNotIn("session-value", json.dumps(active_health))
        self.assertNotIn("browser-value", json.dumps(active_health))
        self.assertTrue(active_health["sessions"]["flight-portal"]["ready"])
        self.assertTrue(active_health["sessions"]["oa"]["ready"])
        options = self.request("/api/options/lock-types")
        self.assertEqual(options["options"][0]["value"], "TEST")
        result = self.request("/api/execute", "POST", {"endpointId": "flight-stats.query", "parameters": {}})
        self.assertEqual(result["body"], "ok")
        oa_cleared = self.request("/api/session?systemId=oa", "DELETE")
        self.assertTrue(oa_cleared["sessions"]["flight-portal"]["ready"])
        self.assertFalse(oa_cleared["sessions"]["oa"]["ready"])
        cleared = self.request("/api/session", "DELETE")
        self.assertFalse(cleared["sessions"]["flight-portal"]["ready"])
        self.assertNotIn("credentials", cleared)

    def test_source_server_serves_page_catalog_and_shared_theme(self) -> None:
        for path in (
            "/",
            "/app.js",
            "/catalog-view.mjs",
            "/parameter-form.mjs",
            "/response-view.mjs",
            "/catalog/index.json",
            "/theme.css",
            "/theme.js",
        ):
            with urllib.request.urlopen(self.base_url + path, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 20)
                if path == "/app.js":
                    self.assertIn("javascript", response.headers.get_content_type())

    def test_progressive_execution_exposes_each_completed_oa_result(self) -> None:
        started = self.request("/api/execute", "POST", {
            "endpointId": "oa-read.read",
            "parameters": {"count": 2},
            "progressive": True,
        })
        task_id = str(started["taskId"])
        self.assertTrue(self.executor.progress_started.wait(timeout=1))

        running = self.request(f"/api/execute/{task_id}")
        self.assertEqual(running["state"], "running")
        self.assertEqual(len(running["result"]["data"]["tables"][0]["rows"]), 1)

        self.executor.progress_release.set()
        deadline = time.monotonic() + 2
        completed = running
        while completed["state"] == "running" and time.monotonic() < deadline:
            completed = self.request(f"/api/execute/{task_id}")
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(len(completed["result"]["data"]["tables"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
