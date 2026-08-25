from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .manager import RunManager


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True


def create_server(app_directory: Path, port: int = 0, manager: RunManager | None = None) -> WorkbenchServer:
    root = app_directory.resolve()
    public_root = root.parents[2] if len(root.parents) > 2 else root
    run_manager = manager or RunManager(root)

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8")) if raw else {}

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(200, run_manager.snapshot()); return
            if parsed.path == "/api/download":
                path = run_manager.download_path()
                if not path:
                    self._json(404, {"error": "当前没有可下载结果"}); return
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", 'attachment; filename="caac-pilot-export.xlsx"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            relative = parsed.path.lstrip("/") or "web/index.html"
            target = (root / "web" / relative).resolve() if not relative.startswith("web/") else (root / relative).resolve()
            if not target.is_file() and relative in {"theme.js", "theme.css", "libs/bootstrap.min.css"}:
                target = (public_root / relative).resolve()
            allowed_roots = (root, public_root)
            is_allowed = any(base == target or base in target.parents for base in allowed_roots)
            if not is_allowed or not target.is_file():
                self._json(404, {"error": "Not Found"}); return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._body()
                if self.path == "/api/session/verify":
                    result = run_manager.verify_credentials(str(payload.get("credentials", "")))
                elif self.path == "/api/run":
                    result = run_manager.run()
                elif self.path == "/api/stop":
                    result = run_manager.stop()
                else:
                    self._json(404, {"error": "Not Found"}); return
                self._json(200, result)
            except (ValueError, RuntimeError) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self._json(500, {"error": str(error)})

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = WorkbenchServer(("127.0.0.1", port), Handler)
    server.run_manager = run_manager  # type: ignore[attr-defined]
    return server
