"""Loopback server for the SOC positioning workbench."""

from __future__ import annotations

import base64
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .manager import RunManager
from .models import InputPayload


def payload_from_json(payload: dict[str, object]) -> InputPayload:
    encoded = str(payload.get("excelBase64", "") or "")
    try:
        content = base64.b64decode(encoded, validate=True) if encoded else None
    except ValueError as error:
        raise ValueError("Excel 文件内容不是有效 Base64") from error
    return InputPayload(
        input_mode=str(payload.get("inputMode", "excel") or "excel"),
        excel_name=str(payload.get("excelName", "") or ""), excel_bytes=content,
        pasted_text=str(payload.get("pastedText", "") or ""), common_remark=str(payload.get("commonRemark", "") or ""),
    )


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True


def create_server(app_directory: Path, port: int = 0, manager: RunManager | None = None) -> WorkbenchServer:
    app_directory = app_directory.resolve()
    run_manager = manager or RunManager(app_directory)
    web_root = app_directory / "web"
    shared_static_root = app_directory.parents[2] if len(app_directory.parents) >= 3 else app_directory

    def workbench_asset(relative_path: str, shared_path: str) -> Path:
        packaged_path = web_root / relative_path
        return packaged_path if packaged_path.is_file() else shared_static_root / shared_path

    class Handler(BaseHTTPRequestHandler):
        server_version = "HttpSocPositioning/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _payload(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8") if length else "{}")
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("请求内容不是有效 JSON") from error
            if not isinstance(value, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            return value

        def _file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix in {".mjs", ".js", ".css"}:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/status":
                self._json(run_manager.snapshot())
                return
            if path == "/api/download/result":
                result = run_manager.download_path()
                if result is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                content = result.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", 'attachment; filename="soc-positioning-result.xlsx"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            mapping = {
                "/": web_root / "index.html",
                "/index.html": web_root / "index.html",
                "/app.mjs": web_root / "app.mjs",
                "/session_keepalive.mjs": web_root / "session_keepalive.mjs",
                "/styles.css": web_root / "styles.css",
                "/template.xlsx": web_root / "template.xlsx",
                "/theme.js": workbench_asset("theme.js", "theme.js"),
                "/theme.css": workbench_asset("theme.css", "theme.css"),
                "/libs/bootstrap.min.css": workbench_asset("libs/bootstrap.min.css", "libs/bootstrap.min.css"),
            }
            filename = mapping.get(path)
            if filename:
                self._file(filename)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._payload()
                if path == "/api/session/verify":
                    value = run_manager.verify(str(payload.get("credentials", "") or ""))
                elif path == "/api/check-data":
                    value = run_manager.check_data(payload_from_json(payload))
                elif path == "/api/run":
                    value = run_manager.run(payload_from_json(payload))
                elif path == "/api/stop":
                    value = run_manager.stop()
                else:
                    self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(value)
            except Exception as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
