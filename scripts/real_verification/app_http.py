"""独立 APP 的 loopback HTTP 真实验收工具。"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from html.parser import HTMLParser
from typing import Generator
from urllib.parse import urlsplit

import requests


FINAL_PHASES = {
    "completed",
    "partial_failure",
    "failed",
    "session_expired",
    "stopped",
    "terminated",
}
REQUIRED_RUNTIME_ASSETS = {
    "/theme.js",
    "/libs/bootstrap.min.css",
    "/theme.css",
    "/styles.css",
}
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
)


class _RuntimeAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        reference = values.get("src") if tag == "script" else values.get("href") if tag == "link" else None
        if not reference or urlsplit(reference).netloc:
            return
        path = "/" + urlsplit(reference).path.lstrip("./")
        self.paths.add(path)


@contextmanager
def serve_app(server: object, manager: object) -> Generator[str, None, None]:
    thread = threading.Thread(target=server.serve_forever, name="real-app-verification", daemon=True)  # type: ignore[attr-defined]
    thread.start()
    host, port = server.server_address  # type: ignore[attr-defined]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]
        thread.join(timeout=5)
        shutdown = getattr(manager, "shutdown", None)
        if callable(shutdown):
            shutdown()
        else:
            client = getattr(manager, "client", None)
            close = getattr(client, "close", None)
            if callable(close):
                close()


def get_json(base_url: str, path: str) -> dict[str, object]:
    response = requests.get(
        f"{base_url}{path}",
        headers={"User-Agent": DEFAULT_BROWSER_USER_AGENT},
        timeout=30,
    )
    return _json_response(response, path)


def post_json(base_url: str, path: str, payload: dict[str, object]) -> dict[str, object]:
    response = requests.post(
        f"{base_url}{path}",
        json=payload,
        headers={"User-Agent": DEFAULT_BROWSER_USER_AGENT},
        timeout=60,
    )
    return _json_response(response, path)


def _require_runtime_asset(base_url: str, path: str) -> requests.Response:
    response = requests.get(
        f"{base_url}{path}",
        headers={"User-Agent": DEFAULT_BROWSER_USER_AGENT},
        timeout=30,
    )
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"APP 本地服务没有返回运行资源 {path}")
    return response


def verify_frontend_route(base_url: str, route: str) -> None:
    page = requests.get(
        f"{base_url}/",
        headers={"User-Agent": DEFAULT_BROWSER_USER_AGENT},
        timeout=30,
    )
    if page.status_code != 200 or not page.content:
        raise RuntimeError("APP 本地服务没有返回首页")
    parser = _RuntimeAssetParser()
    parser.feed(page.text)
    for path in sorted(REQUIRED_RUNTIME_ASSETS):
        if path not in parser.paths:
            raise RuntimeError(f"APP 首页没有声明运行资源 {path}")
        _require_runtime_asset(base_url, path)
    response = _require_runtime_asset(base_url, "/app.mjs")
    if route not in response.text:
        raise RuntimeError(f"APP 前端没有绑定后端路由 {route}")
    _require_runtime_asset(base_url, "/session_keepalive.mjs")


def wait_for_final(base_url: str, *, timeout_seconds: int = 180) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = get_json(base_url, "/api/status")
        phase = str(state.get("phase") or "")
        if phase in FINAL_PHASES:
            return state
        time.sleep(0.25)
    raise TimeoutError("APP 真实任务未在限定时间内结束")


def require_completed(state: dict[str, object], *, minimum_success: int = 1) -> dict[str, object]:
    phase = str(state.get("phase") or "")
    if phase == "session_expired":
        raise RuntimeError("APP 真实任务确认登录凭据已失效")
    progress = state.get("progress")
    success = int(progress.get("success") or 0) if isinstance(progress, dict) else 0
    if phase != "completed" or success < minimum_success:
        failed_items = [
            str(item.get("error") or "").strip()
            for item in state.get("items", [])
            if isinstance(item, dict) and item.get("status") == "failed" and item.get("error")
        ] if isinstance(state.get("items"), list) else []
        message = str(state.get("error") or state.get("message") or (failed_items[0] if failed_items else phase))
        raise RuntimeError(f"APP 真实任务未成功完成：{message}")
    return state


def _json_response(response: requests.Response, path: str) -> dict[str, object]:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"APP 路由 {path} 未返回 JSON") from error
    if response.status_code != 200:
        message = payload.get("error") if isinstance(payload, dict) else ""
        raise RuntimeError(f"APP 路由 {path} 返回 HTTP {response.status_code}：{message}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"APP 路由 {path} 响应根节点不是对象")
    return payload


__all__ = [
    "get_json",
    "post_json",
    "require_completed",
    "serve_app",
    "verify_frontend_route",
    "wait_for_final",
]
