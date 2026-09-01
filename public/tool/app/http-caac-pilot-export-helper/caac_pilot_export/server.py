from __future__ import annotations

import base64
import binascii
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .manager import RunManager
from .models import InputPayload


def payload_from_json(payload: dict[str, object]) -> InputPayload:
    encoded = str(payload.get("excelBase64", "") or "")
    try:
        content = base64.b64decode(encoded, validate=True) if encoded else None
    except (ValueError, binascii.Error) as error:
        raise ValueError("Excel 文件内容不是有效 Base64") from error
    return InputPayload(str(payload.get("excelName", "") or ""), content)


class WorkbenchServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_server(app_directory: Path, port: int = 0, manager: RunManager | None = None) -> WorkbenchServer:
    root = app_directory.resolve()
    web_root = root / "web"
    shared_static_root = root.parents[2] if len(root.parents) >= 3 else root
    run_manager = manager or RunManager(root)

    def workbench_asset(relative_path: str, shared_path: str) -> Path:
        packaged_path = web_root / relative_path
        return packaged_path if packaged_path.is_file() else shared_static_root / shared_path

    class Handler(BaseHTTPRequestHandler):
        server_version = "CaacPilotExport/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("请求内容不是有效 JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            return payload

        def _file(self, target: Path) -> None:
            if not target.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not Found"})
                return
            body = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or target.suffix in {".js", ".mjs", ".css"}:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _excel(self, body: bytes, filename: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(HTTPStatus.OK, run_manager.snapshot())
                return
            if parsed.path == "/api/results":
                query = parse_qs(parsed.query)
                offset = int(query.get("offset", ["0"])[0])
                limit = int(query.get("limit", ["50"])[0])
                self._json(HTTPStatus.OK, run_manager.results_page(offset, limit))
                return
            if parsed.path == "/api/download":
                result = run_manager.download_path()
                if result is None:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "当前没有可下载结果"})
                    return
                self._excel(result.read_bytes(), result.name)
                return
            static_map = {
                "/": web_root / "index.html",
                "/index.html": web_root / "index.html",
                "/app.mjs": web_root / "app.mjs",
                "/results_table.mjs": web_root / "results_table.mjs",
                "/session_keepalive.mjs": web_root / "session_keepalive.mjs",
                "/styles.css": web_root / "styles.css",
                "/theme.js": workbench_asset("theme.js", "theme.js"),
                "/theme.css": workbench_asset("theme.css", "theme.css"),
                "/libs/bootstrap.min.css": workbench_asset("libs/bootstrap.min.css", "libs/bootstrap.min.css"),
            }
            target = static_map.get(parsed.path)
            if target is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not Found"})
                return
            self._file(target)

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._body()
                path = urlparse(self.path).path
                if path == "/api/session/verify":
                    result = run_manager.verify_credentials(str(payload.get("credentials", "") or ""))
                elif path == "/api/check-data":
                    result = run_manager.check_data(str(payload.get("mode", "all") or "all"), payload_from_json(payload))
                elif path == "/api/run":
                    result = run_manager.run(str(payload.get("mode", "all") or "all"), payload_from_json(payload))
                elif path == "/api/stop":
                    result = run_manager.stop()
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "Not Found"})
                    return
                self._json(HTTPStatus.OK, result)
            except Exception as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
