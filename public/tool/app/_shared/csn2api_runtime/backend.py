from __future__ import annotations

import http.client

from .supervisor import RuntimeSupervisor


def request_backend(
    supervisor: RuntimeSupervisor,
    entry: str,
    method: str,
    target_path: str,
    body: bytes | None,
    headers: dict[str, str],
) -> tuple[int, list[tuple[str, str]], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", supervisor.port(entry), timeout=180)
    try:
        connection.request(method, target_path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, list(response.getheaders()), response.read()
    finally:
        connection.close()


__all__ = ["request_backend"]
