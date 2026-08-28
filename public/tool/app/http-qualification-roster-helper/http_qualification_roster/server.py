from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from .manager import RunManager


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True


def _asset(app_root: Path, relative: str) -> Path:
    local = app_root / relative
    return local if local.is_file() else app_root.parents[2] / relative


def create_server(
    app_root: Path,
    port: int = 0,
    manager: RunManager | None = None,
) -> WorkbenchServer:
    root = Path(app_root).resolve()
    web_root = root / "web"
    run_manager = manager or RunManager(root / "results")

    class Handler(BaseHTTPRequestHandler):
        server_version = "csn2api-qualification-roster/1"

        def log_message(self, _format: str, *_args: object) -> None:
            return None

        def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1024 * 1024:
                raise ValueError("请求体过大")
            value = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(value, dict):
                raise ValueError("请求体必须是 JSON 对象")
            return value

        def _serve_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/status":
                self._send_json(run_manager.snapshot())
                return
            if path == "/api/download/excel":
                result = run_manager.download_path()
                if result is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = result.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(result.name)}")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            static = {
                "/": web_root / "index.html",
                "/index.html": web_root / "index.html",
                "/app.mjs": web_root / "app.mjs",
                "/session_keepalive.mjs": web_root / "session_keepalive.mjs",
                "/styles.css": web_root / "styles.css",
                "/theme.css": _asset(root, "theme.css"),
                "/theme.js": _asset(root, "theme.js"),
                "/libs/bootstrap.min.css": _asset(root, "libs/bootstrap.min.css"),
            }.get(path)
            if static is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._serve_file(static)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/api/session/verify":
                    result = run_manager.verify_credentials(str(payload.get("credentials", "") or ""))
                elif path == "/api/metadata/load":
                    result = run_manager.load_metadata()
                elif path == "/api/run":
                    result = run_manager.start_query(payload)
                elif path == "/api/stop":
                    result = run_manager.stop()
                else:
                    self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
            except Exception as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
