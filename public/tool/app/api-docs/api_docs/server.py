from __future__ import annotations

import copy
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread, current_thread
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from .catalog import ApiCatalog
from .executor import ApiExecutor
from universal_query import UniversalQueryError, UniversalQueryService


class ApiDocsServer(ThreadingHTTPServer):
    daemon_threads = True


class ExecutionTaskStore:
    def __init__(self, executor: ApiExecutor, catalog: ApiCatalog) -> None:
        self.executor = executor
        self.catalog = catalog
        self.lock = Lock()
        self.tasks: dict[str, dict[str, object]] = {}
        self.active_systems: dict[str, str] = {}
        self.workers: dict[str, Thread] = {}
        self.closing = False

    def start(self, endpoint_id: str, parameters: dict[str, object]) -> dict[str, object]:
        record = self.catalog.get_endpoint(endpoint_id)
        if record.endpoint.get("progressive") is not True:
            raise ValueError("当前接口不支持渐进执行")
        system_id = str(record.module.get("systemId", ""))
        with self.lock:
            if self.closing:
                raise RuntimeError("API 文档正在关闭，不能启动新任务")
            if system_id in self.active_systems:
                raise ValueError("当前系统已有任务正在执行")
            task_id = uuid4().hex
            self.tasks[task_id] = {
                "taskId": task_id,
                "endpointId": endpoint_id,
                "state": "running",
                "result": None,
            }
            self.active_systems[system_id] = task_id
            worker = Thread(
                target=self._run,
                args=(task_id, system_id, endpoint_id, parameters),
                name=f"api-docs-{system_id}-execution",
                daemon=True,
            )
            self.workers[task_id] = worker
            worker.start()
        return self.status(task_id)

    def status(self, task_id: str) -> dict[str, object]:
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise ValueError("本地任务不存在")
            return copy.deepcopy(task)

    def _run(
        self,
        task_id: str,
        system_id: str,
        endpoint_id: str,
        parameters: dict[str, object],
    ) -> None:
        def report(result: dict[str, object]) -> None:
            with self.lock:
                self.tasks[task_id]["result"] = copy.deepcopy(result)

        try:
            result = self.executor.execute(endpoint_id, parameters, report)
        except Exception as error:
            with self.lock:
                self.tasks[task_id]["state"] = "failed"
                self.tasks[task_id]["error"] = str(error)
        else:
            with self.lock:
                self.tasks[task_id]["state"] = "completed"
                self.tasks[task_id]["result"] = copy.deepcopy(result)
        finally:
            with self.lock:
                if self.active_systems.get(system_id) == task_id:
                    self.active_systems.pop(system_id, None)
                self.workers.pop(task_id, None)

    def close(self) -> None:
        with self.lock:
            self.closing = True
            workers = list(self.workers.values())
        for worker in workers:
            if worker is not current_thread() and worker.is_alive():
                worker.join()


def create_server(
    app_directory: Path,
    port: int = 0,
    executor: ApiExecutor | None = None,
) -> ApiDocsServer:
    app_directory = app_directory.resolve()
    catalog = executor.catalog if executor is not None else ApiCatalog(app_directory / "catalog")
    request_executor = executor or ApiExecutor(catalog)
    execution_tasks = ExecutionTaskStore(request_executor, catalog)
    universal_query = UniversalQueryService(catalog, request_executor, execution_tasks)
    shared_static_root = app_directory.parents[2] if len(app_directory.parents) >= 3 else app_directory

    def shared_asset(relative_path: str) -> Path:
        packaged = app_directory / relative_path
        return packaged if packaged.is_file() else shared_static_root / relative_path

    class Handler(BaseHTTPRequestHandler):
        server_version = "Csn2ApiDocs/1.0"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("请求内容不是有效 JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            return payload

        def _serve_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or path.suffix in {".js", ".mjs", ".css", ".json"}:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _static_path(self, request_path: str) -> Path | None:
            fixed = {
                "/": app_directory / "index.html",
                "/index.html": app_directory / "index.html",
                "/styles.css": app_directory / "styles.css",
                "/app.js": (app_directory / "app.js") if (app_directory / "app.js").is_file() else (app_directory / "app.mjs"),
                "/theme.js": shared_asset("theme.js"),
                "/theme.css": shared_asset("theme.css"),
            }
            if request_path in fixed:
                return fixed[request_path]
            if request_path.endswith(".mjs") and request_path.count("/") == 1:
                candidate = (app_directory / unquote(request_path.lstrip("/"))).resolve()
                try:
                    candidate.relative_to(app_directory)
                except ValueError:
                    return None
                return candidate
            if request_path.startswith("/catalog/"):
                candidate = (app_directory / unquote(request_path.lstrip("/"))).resolve()
                try:
                    candidate.relative_to(app_directory / "catalog")
                except ValueError:
                    return None
                return candidate
            return None

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/api/universal-query/v1"):
                try:
                    if path == "/api/universal-query/v1/health":
                        self._send_json(universal_query.health())
                    elif path == "/api/universal-query/v1/sessions":
                        self._send_json(universal_query.sessions())
                    elif path == "/api/universal-query/v1/operations":
                        self._send_json(universal_query.operations())
                    elif path.startswith("/api/universal-query/v1/options/"):
                        source_id = unquote(path.removeprefix("/api/universal-query/v1/options/"))
                        self._send_json(universal_query.options(source_id))
                    elif path.startswith("/api/universal-query/v1/operations/"):
                        operation_id = unquote(path.removeprefix("/api/universal-query/v1/operations/"))
                        self._send_json(universal_query.operation(operation_id))
                    elif path.startswith("/api/universal-query/v1/executions/"):
                        run_id = unquote(path.removeprefix("/api/universal-query/v1/executions/"))
                        self._send_json(universal_query.execution(run_id))
                    else:
                        self._send_json(universal_query.error_response(
                            UniversalQueryError("route_not_found", "接口不存在"),
                        ), HTTPStatus.NOT_FOUND)
                except Exception as error:
                    self._send_json(universal_query.error_response(error), HTTPStatus.BAD_REQUEST)
                return
            if path == "/api/health":
                self._send_json({"available": True, "sessions": request_executor.all_session_statuses()})
                return
            if path == "/api/credentials":
                self._send_json(request_executor.export_credential_bundle())
                return
            if path == "/api/catalog":
                self._send_json(catalog.as_dict())
                return
            if path.startswith("/api/execute/"):
                try:
                    task_id = unquote(path.removeprefix("/api/execute/"))
                    self._send_json(execution_tasks.status(task_id))
                except Exception as error:
                    self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            if path.startswith("/api/options/"):
                try:
                    source = unquote(path.removeprefix("/api/options/"))
                    self._send_json({"options": request_executor.load_options(source)})
                except Exception as error:
                    self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                return
            static_path = self._static_path(path)
            if static_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._serve_file(static_path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path.startswith("/api/universal-query/v1"):
                    if path.startswith("/api/universal-query/v1/sessions/"):
                        system_id = unquote(path.removeprefix("/api/universal-query/v1/sessions/"))
                        result = universal_query.load_session(system_id, payload.get("credential"))
                        self._send_json(result)
                        return
                    if path == "/api/universal-query/v1/executions":
                        result, accepted = universal_query.execute(
                            payload.get("operation"),
                            payload.get("parameters", {}),
                        )
                        self._send_json(result, HTTPStatus.ACCEPTED if accepted else HTTPStatus.OK)
                        return
                    self._send_json(universal_query.error_response(
                        UniversalQueryError("route_not_found", "接口不存在"),
                    ), HTTPStatus.NOT_FOUND)
                    return
                if path == "/api/session":
                    result = request_executor.load_credentials(
                        str(payload.get("credentials", "") or ""),
                        str(payload.get("systemId", "") or ""),
                    )
                elif path == "/api/credentials":
                    result = request_executor.import_credential_bundle(payload)
                elif path == "/api/execute":
                    parameters = payload.get("parameters", {})
                    if not isinstance(parameters, dict):
                        raise ValueError("接口参数必须是 JSON 对象")
                    endpoint_id = str(payload.get("endpointId", "") or "")
                    if payload.get("progressive") is True:
                        result = execution_tasks.start(endpoint_id, parameters)
                        self._send_json(result, HTTPStatus.ACCEPTED)
                        return
                    result = request_executor.execute(endpoint_id, parameters)
                else:
                    self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
            except Exception as error:
                if path.startswith("/api/universal-query/v1"):
                    self._send_json(universal_query.error_response(error), HTTPStatus.BAD_REQUEST)
                else:
                    self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/universal-query/v1"):
                try:
                    if parsed.path.startswith("/api/universal-query/v1/sessions/"):
                        system_id = unquote(parsed.path.removeprefix("/api/universal-query/v1/sessions/"))
                        self._send_json(universal_query.clear_session(system_id))
                    else:
                        self._send_json(universal_query.error_response(
                            UniversalQueryError("route_not_found", "接口不存在"),
                        ), HTTPStatus.NOT_FOUND)
                except Exception as error:
                    self._send_json(universal_query.error_response(error), HTTPStatus.BAD_REQUEST)
                return
            if parsed.path != "/api/session":
                self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            system_id = str(parse_qs(parsed.query).get("systemId", [""])[0] or "")
            request_executor.clear_credentials(system_id or None)
            self._send_json({"sessions": request_executor.all_session_statuses()})

    server = ApiDocsServer(("127.0.0.1", port), Handler)
    server.executor = request_executor  # type: ignore[attr-defined]
    server.execution_tasks = execution_tasks  # type: ignore[attr-defined]
    server.universal_query = universal_query  # type: ignore[attr-defined]
    return server
