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
        self.ready = {"flight-portal": False, "oa": False, "soc": False}
        self.calls: list[tuple[object, ...]] = []
        self.progress_started = threading.Event()
        self.progress_release = threading.Event()

    def session_status(self, system_id="flight-portal") -> dict[str, object]:
        ready = self.ready[system_id]
        if system_id == "soc":
            return {"cookieNames": ["JSESSIONID"] if ready else [], "cookieCount": 1 if ready else 0}
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

    def export_credential_bundle(self) -> dict[str, object]:
        systems = []
        if self.ready["flight-portal"]:
            systems.append({
                "systemId": "flight-portal",
                "credentials": "JSESSIONID=session-value; iebJSid=browser-value",
            })
        if self.ready["oa"]:
            systems.append({
                "systemId": "oa",
                "credentials": "SESSION=oa-value; ROUTE-SESSION=route-value",
            })
        return {
            "format": "csn2api-cookie-bundle",
            "schemaVersion": 1,
            "exportedAt": "2026-08-28T00:00:00+00:00",
            "systems": systems,
        }

    def import_credential_bundle(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict) or not isinstance(payload.get("systems"), list):
            raise ValueError("Cookie 文件无效")
        imported = []
        for item in payload["systems"]:
            self.load_credentials(str(item["credentials"]), str(item["systemId"]))
            imported.append(str(item["systemId"]))
        return {
            "bundle": self.export_credential_bundle(),
            "imported": imported,
            "failed": [],
            "sessions": self.all_session_statuses(),
        }

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
            "body": "private-original-response",
            "headers": {"X-Debug-Header": "private-debug-header"},
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
        self.assertTrue(
            {"flight-stats", "lock-entry", "personnel-info", "oa-read"}.issubset(
                {module["id"] for module in catalog["modules"]}
            )
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
        self.assertEqual(result["body"], "private-original-response")
        oa_cleared = self.request("/api/session?systemId=oa", "DELETE")
        self.assertTrue(oa_cleared["sessions"]["flight-portal"]["ready"])
        self.assertFalse(oa_cleared["sessions"]["oa"]["ready"])
        cleared = self.request("/api/session", "DELETE")
        self.assertFalse(cleared["sessions"]["flight-portal"]["ready"])
        self.assertNotIn("credentials", cleared)

    def test_exports_and_imports_one_cookie_bundle(self) -> None:
        self.request(
            "/api/session",
            "POST",
            {"systemId": "flight-portal", "credentials": "secret-cookie-text"},
        )
        exported = self.request("/api/credentials")
        self.assertEqual(exported["format"], "csn2api-cookie-bundle")
        self.assertEqual(exported["systems"][0]["systemId"], "flight-portal")

        self.request("/api/session", "DELETE")
        imported = self.request("/api/credentials", "POST", exported)
        self.assertEqual(imported["imported"], ["flight-portal"])
        self.assertTrue(imported["sessions"]["flight-portal"]["ready"])

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

    def test_universal_query_exposes_dynamic_operations_and_safe_results(self) -> None:
        operations = self.request("/api/universal-query/v1/operations")
        self.assertTrue(operations["ok"])
        self.assertEqual(
            {item["operation"] for item in operations["operations"]},
            set(self.executor.catalog.endpoints),
        )
        flight_stats = next(
            item for item in operations["operations"]
            if item["operation"] == "flight-stats.query"
        )
        self.assertEqual(flight_stats["systemId"], "flight-portal")
        self.assertEqual(flight_stats["risk"], "read")
        self.assertEqual(
            flight_stats["minimumInput"],
            ["staffNum", "startStr", "endStr"],
        )
        self.assertTrue(any(item["operation"] == "lock-entry.submit" and item["risk"] == "write" for item in operations["operations"]))
        self.assertTrue(any(parameter["name"] == "currentStr" and parameter["mode"] == "automatic" for parameter in flight_stats["parameters"]))
        self.executor.ready["soc"] = True
        self.assertTrue(self.request("/api/universal-query/v1/sessions")["sessions"]["soc"]["ready"])

        session = self.request(
            "/api/universal-query/v1/sessions/flight-portal",
            "POST",
            {"credential": "secret-cookie-text"},
        )
        serialized_session = json.dumps(session)
        self.assertTrue(session["ok"])
        self.assertNotIn("secret-cookie-text", serialized_session)
        self.assertNotIn("session-value", serialized_session)
        self.assertNotIn("browser-value", serialized_session)

        completed = self.request("/api/universal-query/v1/executions", "POST", {
            "operation": "flight-stats.query",
            "parameters": {
                "staffNum": "900001",
                "startStr": "2026-01-01",
                "endStr": "2026-01-31",
            },
        })
        serialized_result = json.dumps(completed)
        self.assertTrue(completed["ok"])
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["result"]["meta"]["status"], 200)
        self.assertEqual(completed["result"]["summary"], {"success": 0})
        self.assertEqual(completed["result"]["tables"][0]["id"], "results")
        self.assertNotIn("body", completed["result"])
        self.assertNotIn("headers", completed["result"])
        self.assertNotIn("private-original-response", serialized_result)
        self.assertNotIn("private-debug-header", serialized_result)

    def test_universal_query_materializes_defaults_and_polls_progressive_runs(self) -> None:
        self.request(
            "/api/universal-query/v1/sessions/oa",
            "POST",
            {"credential": "oa-cookie-text"},
        )
        started = self.request("/api/universal-query/v1/executions", "POST", {
            "operation": "oa-read.read",
            "parameters": {},
        })
        self.assertEqual(started["state"], "running")
        self.assertEqual(started["risk"], "write")
        self.assertEqual(self.executor.calls[-1], ("execute", "oa-read.read", {"count": "10"}))
        self.assertTrue(self.executor.progress_started.wait(timeout=1))

        running = self.request(f"/api/universal-query/v1/executions/{started['runId']}")
        self.assertEqual(running["state"], "running")
        self.assertEqual(len(running["result"]["tables"][0]["rows"]), 1)

        self.executor.progress_release.set()
        deadline = time.monotonic() + 2
        completed = running
        while completed["state"] == "running" and time.monotonic() < deadline:
            completed = self.request(f"/api/universal-query/v1/executions/{started['runId']}")
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(len(completed["result"]["tables"][0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
