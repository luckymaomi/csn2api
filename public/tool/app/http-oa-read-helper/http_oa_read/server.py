"""OA HTTP 已阅工作台的 loopback API 与静态文件服务。"""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .manager import RunManager


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}必须是整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name}必须是整数") from error
    return parsed


def create_server(
    app_directory: Path,
    port: int = 0,
    manager: RunManager | object | None = None,
) -> WorkbenchServer:
    app_directory = app_directory.resolve()
    web_root = app_directory / "web"
    public_root = app_directory.parents[2]
    run_manager = manager or RunManager(app_directory)

    def asset_path(relative_path: str, fallback_path: str) -> Path:
        local_asset = web_root / relative_path
        if local_asset.is_file():
            return local_asset
        return public_root / fallback_path

    class Handler(BaseHTTPRequestHandler):
        server_version = "OAHttpReadWorkbench/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _read_json(self) -> dict[str, object]:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("请求 Content-Length 无效") from error
            if content_length < 0 or content_length > 2_000_000:
                raise ValueError("请求体大小无效")
            raw = self.rfile.read(content_length)
            if not raw:
                return {}
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("请求体必须是 UTF-8 JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("请求体根节点必须是对象")
            return payload

        def _serve_file(self, file_path: Path) -> None:
            if not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = file_path.read_bytes()
            content_type, _ = mimetypes.guess_type(file_path.name)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/status":
                self._send_json(run_manager.snapshot())  # type: ignore[attr-defined]
                return
            static_map = {
                "/": web_root / "index.html",
                "/index.html": web_root / "index.html",
                "/app.mjs": web_root / "app.mjs",
                "/session_keepalive.mjs": web_root / "session_keepalive.mjs",
                "/styles.css": web_root / "styles.css",
                "/theme.js": asset_path("theme.js", "theme.js"),
                "/theme.css": asset_path("theme.css", "theme.css"),
                "/libs/bootstrap.min.css": asset_path("libs/bootstrap.min.css", "libs/bootstrap.min.css"),
            }
            static_path = static_map.get(path)
            if static_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._serve_file(static_path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/api/session/verify":
                    state = run_manager.verify_credentials(str(payload.get("credentials") or ""))  # type: ignore[attr-defined]
                elif path == "/api/session/clear":
                    state = run_manager.clear_session()  # type: ignore[attr-defined]
                elif path == "/api/scan":
                    state = run_manager.scan()  # type: ignore[attr-defined]
                elif path == "/api/run":
                    state = run_manager.run(  # type: ignore[attr-defined]
                        max_count=_integer(payload.get("maxCount", 10), "本次数量"),
                        run_mode=str(payload.get("runMode") or "all"),
                    )
                elif path == "/api/stop":
                    state = run_manager.stop()  # type: ignore[attr-defined]
                elif path == "/api/start":
                    state = run_manager.start(  # type: ignore[attr-defined]
                        credentials=str(payload.get("credentials") or ""),
                        max_count=_integer(payload.get("maxCount", 10), "本次数量"),
                        run_mode=str(payload.get("runMode") or "all"),
                    )
                else:
                    self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(state)
            except Exception as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
