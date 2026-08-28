from __future__ import annotations

import copy
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .backend import request_backend
from .credential_runtime import CredentialRuntime
from .lan_assets import RUNTIME_CSS, RUNTIME_JS
from .lease import AccessLease
from .supervisor import RuntimeSupervisor


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def create_gateway_server(
    dist_root: Path,
    supervisor: RuntimeSupervisor,
    lease: AccessLease,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    static_root = dist_root.resolve()
    credential_runtime = CredentialRuntime(supervisor)

    class Handler(BaseHTTPRequestHandler):
        server_version = "csn2api-lan/1"

        def log_message(self, format_string: str, *args: object) -> None:
            print(f"[csn2api] {self.client_address[0]} {format_string % args}")

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch()

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch()

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch()

        def _dispatch(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path in {"", "/", "/tool"}:
                self._redirect("/tool/")
                return
            if parsed.path.startswith("/__runtime__/"):
                self._runtime(parsed.path)
                return
            if parsed.path == "/api-docs":
                self._redirect("/api-docs/")
                return
            if parsed.path.startswith("/apps/") and "/" not in parsed.path.removeprefix("/apps/"):
                self._redirect(f"{parsed.path}/")
                return
            route = self._target_route(parsed.path)
            if route is not None:
                entry, backend_path = route
                self._proxy(entry, backend_path, parsed.query)
                return
            if self.command != "GET":
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            self._static(parsed.path)

        def _target_route(self, request_path: str) -> tuple[str, str] | None:
            if request_path.startswith("/api-docs/"):
                return "api-docs", "/" + request_path.removeprefix("/api-docs/")
            if not request_path.startswith("/apps/"):
                return None
            remainder = request_path.removeprefix("/apps/")
            entry, separator, child_path = remainder.partition("/")
            if entry not in supervisor.targets:
                return None
            return entry, "/" + child_path

        def _proxy(self, entry: str, backend_path: str, query: str) -> None:
            with supervisor.lock:
                decision = lease.authorize(self.client_address[0], entry, busy=supervisor.busy())
                if not decision.allowed:
                    self._locked(decision.owner_ip, decision.entry, backend_path)
                    return
                if decision.requires_reset:
                    supervisor.restart_all()
                content_length = int(self.headers.get("Content-Length", "0") or 0)
                body = self.rfile.read(content_length) if content_length else None
                headers = {
                    name: value
                    for name, value in self.headers.items()
                    if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "content-length"}
                }
                target_path = backend_path or "/"
                if query:
                    target_path += f"?{query}"
                try:
                    status, response_headers, content = request_backend(
                        supervisor,
                        entry,
                        self.command,
                        target_path,
                        body,
                        headers,
                    )
                except OSError as error:
                    self._json({"error": f"工作台暂不可用：{error}"}, HTTPStatus.BAD_GATEWAY)
                    return
                content_type = next(
                    (value for name, value in response_headers if name.lower() == "content-type"),
                    "",
                )
                if "text/html" in content_type and status == HTTPStatus.OK:
                    content = self._inject_runtime(content)
                self.send_response(status)
                for name, value in response_headers:
                    if name.lower() not in HOP_BY_HOP_HEADERS | {"content-length"}:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        def _runtime(self, path: str) -> None:
            if path == "/__runtime__/client.js" and self.command == "GET":
                self._bytes(RUNTIME_JS.encode("utf-8"), "text/javascript; charset=utf-8")
                return
            if path == "/__runtime__/client.css" and self.command == "GET":
                self._bytes(RUNTIME_CSS.encode("utf-8"), "text/css; charset=utf-8")
                return
            if path == "/__runtime__/credentials" and self.command in {"GET", "POST"}:
                self._runtime_credentials()
                return
            if path == "/__runtime__/status" and self.command == "GET":
                value = copy.deepcopy(lease.snapshot())
                value["youOwn"] = value.get("ownerIp") == self.client_address[0]
                value["busy"] = supervisor.busy()
                self._json(value)
                return
            if path == "/__runtime__/heartbeat" and self.command == "POST":
                if lease.heartbeat(self.client_address[0]):
                    self._json({"ok": True})
                else:
                    self._json({"error": "当前工作台由其他用户占用"}, HTTPStatus.LOCKED)
                return
            if path == "/__runtime__/release" and self.command == "POST":
                with supervisor.lock:
                    busy = supervisor.busy()
                    if not lease.release(self.client_address[0], busy=busy):
                        status = HTTPStatus.CONFLICT if busy else HTTPStatus.LOCKED
                        self._json({"error": "当前任务运行中或工作台不属于你"}, status)
                        return
                    supervisor.restart_all()
                self._json({"ok": True})
                return
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

        def _runtime_credentials(self) -> None:
            with supervisor.lock:
                decision = lease.authorize(self.client_address[0], "api-docs", busy=supervisor.busy())
                if not decision.allowed:
                    self._json(
                        {"error": "当前工作台正在使用中，请稍后再试", "ownerIp": decision.owner_ip},
                        HTTPStatus.LOCKED,
                    )
                    return
                if decision.requires_reset:
                    supervisor.restart_all()
                body = None
                if self.command == "POST":
                    content_length = int(self.headers.get("Content-Length", "0") or 0)
                    body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    status, result = credential_runtime.request(self.command, body)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    self._json({"error": f"Cookie 服务暂不可用：{error}"}, HTTPStatus.BAD_GATEWAY)
                    return
                if status >= 400:
                    self._json(result, HTTPStatus(status))
                    return
                self._json(result)

        def _static(self, request_path: str) -> None:
            relative = unquote(request_path.lstrip("/"))
            candidate = (static_root / relative).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if candidate.is_dir():
                candidate /= "index.html"
            if not candidate.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = candidate.read_bytes()
            mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if candidate == static_root / "tool" / "index.html":
                content = content.replace(
                    b"</head>",
                    b'<script>window.Csn2ApiRuntime={mode:"lan"};</script>\n</head>',
                )
            if mime.startswith("text/") or candidate.suffix in {".js", ".mjs", ".css", ".json"}:
                mime += "; charset=utf-8"
            self._bytes(content, mime)

        def _locked(self, owner_ip: str, entry: str, backend_path: str) -> None:
            accepts_html = "text/html" in self.headers.get("Accept", "") or backend_path in {"/", "/index.html"}
            if not accepts_html:
                self._json(
                    {"error": "当前工作台正在使用中，请稍后再试", "ownerIp": owner_ip, "entry": entry},
                    HTTPStatus.LOCKED,
                )
                return
            html = f"""<!DOCTYPE html><html lang="zh-CN" data-default-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>工作台正在使用中</title><script src="/theme.js"></script><link rel="stylesheet" href="/theme.css"><style>body{{margin:0;background:var(--soft-bg);color:var(--soft-ink);font-family:\"Microsoft YaHei UI\",sans-serif}}main{{width:min(560px,calc(100% - 32px));margin:12vh auto;padding:28px;border:2px solid var(--soft-border);background:var(--soft-surface);box-shadow:var(--hard-shadow-medium)}}h1{{font-size:22px}}p{{color:var(--soft-muted)}}a{{color:var(--soft-ink)}}</style></head><body><main><h1>当前工作台正在使用中</h1><p>使用者 IP：{owner_ip}</p><p>请稍后再试。</p><a href="/tool/index.html">返回工具首页</a></main></body></html>"""
            self._bytes(html.encode("utf-8"), "text/html; charset=utf-8", HTTPStatus.LOCKED)

        @staticmethod
        def _inject_runtime(content: bytes) -> bytes:
            head = b'<script>window.Csn2ApiRuntime={mode:"lan"};</script>\n<link rel="stylesheet" href="/__runtime__/client.css">\n</head>'
            body = b'<script src="/__runtime__/client.js"></script>\n</body>'
            content = content.replace(b"</head>", head, 1)
            return content.replace(b"</body>", body, 1)

        def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._bytes(
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _bytes(
            self,
            content: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


__all__ = ["create_gateway_server"]
