from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .manager import RunManager


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True


def create_server(app_directory: Path, port: int = 0, manager: RunManager | None = None) -> WorkbenchServer:
    app_directory = app_directory.resolve()
    run_manager = manager or RunManager(app_directory)
    web_root = app_directory / "web"
    shared_root = app_directory.parents[2] if len(app_directory.parents) >= 3 else app_directory

    def asset(local: str, shared: str) -> Path:
        local_path = web_root / local
        return local_path if local_path.is_file() else shared_root / shared

    class Handler(BaseHTTPRequestHandler):
        server_version = "HttpFlightDetail/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def read_json(self) -> dict[str, object]:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}"
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("请求内容不是有效 JSON") from error
            if not isinstance(value, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            return value

        def serve_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or path.suffix in {".js", ".mjs", ".css"}:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/status":
                self.send_json(run_manager.snapshot())
                return
            if path == "/api/results":
                query = parse_qs(urlparse(self.path).query)
                kind = query.get("kind", ["status"])[0]
                offset = query.get("offset", ["0"])[0]
                limit = query.get("limit", ["50"])[0]
                try:
                    payload = run_manager.results_page(kind, int(offset), int(limit))
                except (TypeError, ValueError) as error:
                    self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(payload)
                return
            if path == "/api/download/result":
                result = run_manager.download_path()
                if result is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content = result.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(result.name)}")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            static = {
                "/": web_root / "index.html", "/index.html": web_root / "index.html",
                "/app.mjs": web_root / "app.mjs", "/styles.css": web_root / "styles.css",
                "/session_keepalive.mjs": asset("session_keepalive.mjs", "tool/app/_shared/session_keepalive.mjs"),
                "/theme.js": asset("theme.js", "theme.js"), "/theme.css": asset("theme.css", "theme.css"),
                "/libs/bootstrap.min.css": asset("libs/bootstrap.min.css", "libs/bootstrap.min.css"),
            }.get(path)
            if static is None:
                self.send_error(HTTPStatus.NOT_FOUND)
            else:
                self.serve_file(static)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self.read_json()
                if path == "/api/session/verify":
                    state = run_manager.verify_credentials(str(payload.get("credentials", "") or ""))
                elif path == "/api/check-data":
                    state = run_manager.check_data_from_json(payload)
                elif path == "/api/run":
                    state = run_manager.run_from_json(payload)
                elif path == "/api/stop":
                    state = run_manager.stop()
                else:
                    self.send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self.send_json(state)
            except Exception as error:  # noqa: BLE001 - 转换为本地 API 错误
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
