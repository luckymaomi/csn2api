from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SHARED_ROOT = ROOT / "public" / "tool" / "app" / "_shared"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from csn2api_runtime.lease import AccessLease  # noqa: E402
from csn2api_runtime.gateway import create_gateway_server  # noqa: E402
from csn2api_runtime.credential_runtime import CredentialRuntime  # noqa: E402
from csn2api_runtime.lan_assets import RUNTIME_CSS, RUNTIME_JS  # noqa: E402
from csn2api_runtime.supervisor import RuntimeSupervisor, RuntimeTarget  # noqa: E402
from start_all import load_targets  # noqa: E402


MODULE_SPECIFIER_PATTERN = re.compile(
    r'''(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)["'](\.[^"']+)["']'''
)


class PageAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.assets.append((str(values["src"]), values.get("type") == "module"))
        elif tag == "link" and values.get("href"):
            self.assets.append((str(values["href"]), False))
        elif tag in {"img", "source"} and values.get("src"):
            self.assets.append((str(values["src"]), False))


class MutableClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class AccessLeaseTests(unittest.TestCase):
    def test_other_client_can_observe_shared_runtime_and_take_over(self) -> None:
        clock = MutableClock()
        lease = AccessLease(idle_timeout_seconds=30, clock=clock)

        lease.observe("10.0.0.11", "flight-stats", busy=False)
        lease.observe("10.0.0.12", "lock-entry", busy=False)
        self.assertEqual(lease.snapshot()["ownerIp"], "10.0.0.11")
        self.assertFalse(lease.heartbeat("10.0.0.12"))

        lease.takeover("10.0.0.12", "lock-entry")
        self.assertEqual(lease.snapshot()["ownerIp"], "10.0.0.12")
        self.assertTrue(lease.release("10.0.0.12", busy=False))
        self.assertFalse(lease.snapshot()["occupied"])

    def test_idle_expiry_changes_only_the_advisory_owner(self) -> None:
        clock = MutableClock()
        lease = AccessLease(idle_timeout_seconds=30, clock=clock)
        lease.observe("10.0.0.11", "flight-stats", busy=False)
        clock.value += 31

        lease.observe("10.0.0.12", "lock-entry", busy=True)
        self.assertEqual(lease.snapshot()["ownerIp"], "10.0.0.11")

        lease.observe("10.0.0.12", "lock-entry", busy=False)
        self.assertEqual(lease.snapshot()["ownerIp"], "10.0.0.12")


class RuntimeAssetTests(unittest.TestCase):
    def test_cookie_files_are_managed_only_from_api_docs_in_lan_mode(self) -> None:
        self.assertNotIn("导入 Cookie", RUNTIME_JS)
        self.assertNotIn("导出 Cookie", RUNTIME_JS)
        self.assertIn("/api-docs/", RUNTIME_JS)
        self.assertIn("接管使用", RUNTIME_JS)
        self.assertIn('#credentials', RUNTIME_CSS)
        self.assertIn('.credential-panel h2', RUNTIME_JS)
        self.assertIn('window.location.href = "/tool/"', RUNTIME_JS)

        api_docs_page = (
            ROOT / "public" / "tool" / "app" / "api-docs" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="importCookiesButton"', api_docs_page)
        self.assertIn('id="exportCookiesButton"', api_docs_page)


class RuntimeManifestTests(unittest.TestCase):
    def test_build_manifest_discovers_every_workbench(self) -> None:
        manifest_path = ROOT / "dist" / "runtime-tools.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {str(item["entry"]) for item in manifest["tools"]}
        expected = {
            path.name
            for path in (ROOT / "public" / "tool" / "app").glob("http-*-helper")
            if (path / "web" / "index.html").is_file()
        }
        self.assertEqual(entries, expected)
        for item in manifest["tools"]:
            tool_root = ROOT / "public" / "tool" / "app" / str(item["entry"])
            self.assertTrue((tool_root / "start.py").is_file())
            self.assertTrue((tool_root / str(item["package"]) / "server.py").is_file())
            self.assertTrue(str(item["systemId"]))


class FakeApplicationServer:
    server_address = ("127.0.0.1", 12345)

    def serve_forever(self) -> None:
        return


class RuntimeSupervisorTests(unittest.TestCase):
    def test_start_failure_rolls_back_every_started_target(self) -> None:
        first_server = FakeApplicationServer()
        supervisor = RuntimeSupervisor([
            RuntimeTarget("first", "First", ROOT),
            RuntimeTarget("second", "Second", ROOT),
        ])
        with (
            patch(
                "csn2api_runtime.supervisor.create_application_server",
                side_effect=[first_server, RuntimeError("failed")],
            ),
            patch("csn2api_runtime.supervisor.close_application_server") as close_server,
        ):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                supervisor.start_all()

        close_server.assert_called_once_with(first_server, shutdown=True)
        self.assertTrue(all(target.server is None for target in supervisor.targets.values()))

    def test_restart_replaces_servers_and_stop_clears_targets(self) -> None:
        first_server = FakeApplicationServer()
        second_server = FakeApplicationServer()
        supervisor = RuntimeSupervisor([RuntimeTarget("one", "One", ROOT)])
        with (
            patch(
                "csn2api_runtime.supervisor.create_application_server",
                side_effect=[first_server, second_server],
            ),
            patch("csn2api_runtime.supervisor.close_application_server") as close_server,
        ):
            supervisor.start_all()
            supervisor.restart_all()
            self.assertIs(supervisor.targets["one"].server, second_server)
            supervisor.stop_all()

        self.assertEqual(
            [call.args for call in close_server.call_args_list],
            [(first_server,), (second_server,)],
        )
        self.assertTrue(all(call.kwargs == {"shutdown": True} for call in close_server.call_args_list))
        self.assertIsNone(supervisor.targets["one"].server)


class CredentialRuntimeTests(unittest.TestCase):
    def test_import_distributes_one_system_to_every_matching_tool(self) -> None:
        supervisor = RuntimeSupervisor([
            RuntimeTarget("api-docs", "API Docs", ROOT),
            RuntimeTarget("first", "First", ROOT, system_id="flight-portal"),
            RuntimeTarget("second", "Second", ROOT, system_id="flight-portal"),
            RuntimeTarget("other", "Other", ROOT, system_id="soc"),
        ])
        imported = {
            "bundle": {
                "systems": [
                    {"systemId": "flight-portal", "credentials": "JSESSIONID=a; iebJSid=b"},
                    {"systemId": "soc", "credentials": "JSESSIONID=existing"},
                ]
            },
            "imported": ["flight-portal"],
        }
        responses = [
            (200, [], json.dumps(imported).encode("utf-8")),
            (200, [], b'{"ok": true}'),
            (200, [], b'{"ok": true}'),
        ]

        with patch(
            "csn2api_runtime.credential_runtime.request_backend",
            side_effect=responses,
        ) as request_backend:
            status, result = CredentialRuntime(supervisor).request("POST", b"{}")

        self.assertEqual(status, 200)
        self.assertEqual(result["failed"], [])
        self.assertEqual(
            [call.args[1] for call in request_backend.call_args_list],
            ["api-docs", "first", "second"],
        )

    def test_import_records_one_tool_failure_and_continues(self) -> None:
        supervisor = RuntimeSupervisor([
            RuntimeTarget("api-docs", "API Docs", ROOT),
            RuntimeTarget("first", "First", ROOT, system_id="flight-portal"),
            RuntimeTarget("second", "Second", ROOT, system_id="flight-portal"),
        ])
        imported = {
            "bundle": {
                "systems": [
                    {"systemId": "flight-portal", "credentials": "JSESSIONID=a; iebJSid=b"}
                ]
            },
            "imported": ["flight-portal"],
        }
        responses = [
            (200, [], json.dumps(imported).encode("utf-8")),
            (400, [], json.dumps({"error": "Cookie 已失效"}).encode("utf-8")),
            (200, [], b'{"ok": true}'),
        ]

        with patch(
            "csn2api_runtime.credential_runtime.request_backend",
            side_effect=responses,
        ) as request_backend:
            status, result = CredentialRuntime(supervisor).request("POST", b"{}")

        self.assertEqual(status, 200)
        self.assertEqual(result["failed"], [{"entry": "first", "error": "Cookie 已失效"}])
        self.assertEqual(len(request_backend.call_args_list), 3)


class StandaloneArchiveTests(unittest.TestCase):
    def test_every_discovered_archive_starts_and_stops_through_shared_launcher(self) -> None:
        manifest = json.loads((ROOT / "dist" / "runtime-tools.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["tools"])
        for item in manifest["tools"]:
            entry = str(item["entry"])
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                archive_path = ROOT / "dist" / "exports" / f"{entry}.zip"
                with zipfile.ZipFile(archive_path) as archive:
                    archive.extractall(directory)
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
                process = subprocess.Popen(
                    [sys.executable, "-X", "utf8", "start.py", "--no-open"],
                    cwd=directory,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    env=environment,
                    creationflags=creation_flags,
                )
                try:
                    line = process.stdout.readline() if process.stdout is not None else ""
                    match = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
                    if match is None:
                        try:
                            remainder = process.communicate(timeout=5)[0] or ""
                        except subprocess.TimeoutExpired:
                            process.kill()
                            remainder = process.communicate(timeout=5)[0] or ""
                        self.fail(
                            f"{entry} 未输出独立服务地址，退出码 {process.returncode}：\n"
                            f"{line}{remainder}".rstrip()
                        )
                    port = int(match.group(1))
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers.get_content_type(), "text/html")
                        page = response.read().decode("utf-8")
                        self.assertIn('id="credentials"', page)
                        self.assertNotIn("/__runtime__/client.js", page)
                    if os.name == "nt":
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        process.send_signal(signal.SIGINT)
                    self.assertEqual(process.wait(timeout=10), 0)
                    with socket.socket() as probe:
                        probe.settimeout(1)
                        self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    if process.stdout is not None:
                        process.stdout.close()


class StartAllProcessTests(unittest.TestCase):
    def test_unified_runtime_stops_cleanly_and_releases_its_port(self) -> None:
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        environment = {**os.environ, "PYTHONUNBUFFERED": "1"}
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "start_all.py",
                "--no-build",
                "--no-open",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env=environment,
            creationflags=creation_flags,
        )
        try:
            output_lines: list[str] = []
            port = 0
            for _index in range(20):
                line = process.stdout.readline() if process.stdout is not None else ""
                output_lines.append(line)
                match = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
                if match:
                    port = int(match.group(1))
                    break
                if process.poll() is not None:
                    break
            self.assertGreater(port, 0, "".join(output_lines))
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
                self.assertEqual(response.geturl(), f"http://127.0.0.1:{port}/tool/")
                self.assertTrue(response.read())
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGINT)
            self.assertEqual(process.wait(timeout=20), 0)
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()


class LanGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dist_root = ROOT / "dist"
        cls.supervisor = RuntimeSupervisor(load_targets(cls.dist_root))
        cls.supervisor.start_all()
        cls.lease = AccessLease(idle_timeout_seconds=180)
        cls.gateway = create_gateway_server(cls.dist_root, cls.supervisor, cls.lease, "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.gateway.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.gateway.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.gateway.shutdown()
        cls.gateway.server_close()
        cls.thread.join(timeout=5)
        cls.supervisor.stop_all()

    def test_every_discovered_page_loads_its_complete_local_asset_graph(self) -> None:
        manifest = json.loads((self.dist_root / "runtime-tools.json").read_text(encoding="utf-8"))
        pages = [("首页", "/"), ("API 文档", "/api-docs/")]
        pages.extend(
            (str(item["entry"]), f'/apps/{item["entry"]}/')
            for item in manifest["tools"]
        )
        loaded_modules: set[str] = set()

        for label, page_path in pages:
            with self.subTest(page=label):
                request = urllib.request.Request(
                    f"{self.base_url}{page_path}",
                    headers={"Accept": "text/html"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    page = response.read().decode("utf-8")
                    page_url = response.geturl()
                    self.assertEqual(response.headers.get_content_type(), "text/html")
                if page_path == "/":
                    self.assertEqual(page_url, f"{self.base_url}/tool/")

                parser = PageAssetParser()
                parser.feed(page)
                self.assertTrue(parser.assets, f"{label} 没有声明任何页面资源")
                module_urls: list[str] = []
                for asset_path, is_module in parser.assets:
                    asset_url = urljoin(page_url, asset_path)
                    self.assertEqual(urlsplit(asset_url).netloc, urlsplit(self.base_url).netloc)
                    with urllib.request.urlopen(asset_url, timeout=10) as response:
                        content = response.read()
                        self.assertEqual(response.status, 200)
                    self.assertTrue(content, f"{label} 的资源为空：{asset_url}")
                    if is_module:
                        module_urls.append(asset_url)

                while module_urls:
                    module_url = module_urls.pop()
                    if module_url in loaded_modules:
                        continue
                    loaded_modules.add(module_url)
                    with urllib.request.urlopen(module_url, timeout=10) as response:
                        source = response.read().decode("utf-8")
                        self.assertEqual(response.status, 200)
                    self.assertTrue(source, f"{label} 的模块为空：{module_url}")
                    for specifier in MODULE_SPECIFIER_PATTERN.findall(source):
                        dependency_url = urljoin(module_url, specifier)
                        self.assertEqual(
                            urlsplit(dependency_url).netloc,
                            urlsplit(self.base_url).netloc,
                        )
                        module_urls.append(dependency_url)

    def test_serves_every_workbench_and_api_docs_below_one_origin(self) -> None:
        manifest = json.loads((self.dist_root / "runtime-tools.json").read_text(encoding="utf-8"))
        for item in manifest["tools"]:
            entry = str(item["entry"])
            with self.subTest(entry=entry):
                request = urllib.request.Request(
                    f"{self.base_url}/apps/{entry}/",
                    headers={"Accept": "text/html"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    page = response.read().decode("utf-8")
                self.assertIn("/__runtime__/client.js", page)
                with urllib.request.urlopen(f"{self.base_url}/apps/{entry}/api/status", timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("phase", json.loads(response.read().decode("utf-8")))
        with urllib.request.urlopen(f"{self.base_url}/api-docs/api/health", timeout=10) as response:
            self.assertTrue(json.loads(response.read().decode("utf-8"))["available"])

    def test_cookie_bundle_endpoint_uses_api_docs_contract(self) -> None:
        self.lease.takeover("10.0.0.99", "another-tool")
        with urllib.request.urlopen(f"{self.base_url}/__runtime__/credentials", timeout=10) as response:
            bundle = json.loads(response.read().decode("utf-8"))
        self.assertEqual(bundle["format"], "csn2api-cookie-bundle")
        self.assertEqual(bundle["schemaVersion"], 1)
        self.assertEqual(self.lease.snapshot()["ownerIp"], "10.0.0.99")

        request = urllib.request.Request(
            f"{self.base_url}/__runtime__/credentials",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(error.exception.code, 400)
        self.assertIn("格式或版本", json.loads(error.exception.read().decode("utf-8"))["error"])

    def test_other_client_shares_pages_and_can_take_over_without_runtime_restart(self) -> None:
        self.lease.takeover("10.0.0.99", "another-tool")
        html_request = urllib.request.Request(
            f"{self.base_url}/apps/http-flight-stats-helper/",
            headers={"Accept": "text/html"},
        )
        with urllib.request.urlopen(html_request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("/__runtime__/client.js", response.read().decode("utf-8"))
        with urllib.request.urlopen(
            f"{self.base_url}/apps/http-flight-stats-helper/api/status",
            timeout=10,
        ) as response:
            self.assertEqual(response.status, 200)

        with urllib.request.urlopen(f"{self.base_url}/__runtime__/status", timeout=10) as response:
            status = json.loads(response.read().decode("utf-8"))
        self.assertEqual(status["ownerIp"], "10.0.0.99")
        self.assertFalse(status["youOwn"])

        with patch.object(self.supervisor, "restart_all") as restart_all:
            takeover = urllib.request.Request(
                f"{self.base_url}/__runtime__/takeover",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(takeover, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["ownerIp"], "127.0.0.1")

            release = urllib.request.Request(
                f"{self.base_url}/__runtime__/release",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(release, timeout=10) as response:
                self.assertTrue(json.loads(response.read().decode("utf-8"))["ok"])
            restart_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
