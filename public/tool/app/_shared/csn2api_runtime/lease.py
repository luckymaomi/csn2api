from __future__ import annotations

import time
from threading import Lock
from typing import Callable


class AccessLease:
    def __init__(
        self,
        *,
        idle_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if idle_timeout_seconds <= 0:
            raise ValueError("空闲超时必须大于 0")
        self.idle_timeout_seconds = idle_timeout_seconds
        self.clock = clock
        self.lock = Lock()
        self.owner_ip = ""
        self.entry = ""
        self.acquired_at = 0.0
        self.last_seen_at = 0.0

    def observe(self, client_ip: str, entry: str, *, busy: bool) -> dict[str, object]:
        now = self.clock()
        with self.lock:
            if not self.owner_ip:
                self._assign(client_ip, entry, now)
            elif self.owner_ip == client_ip:
                self.entry = entry
                self.last_seen_at = now
            elif now - self.last_seen_at >= self.idle_timeout_seconds and not busy:
                self._assign(client_ip, entry, now)
            return self._snapshot()

    def takeover(self, client_ip: str, entry: str) -> dict[str, object]:
        with self.lock:
            self._assign(client_ip, entry, self.clock())
            return self._snapshot()

    def heartbeat(self, client_ip: str) -> bool:
        with self.lock:
            if self.owner_ip != client_ip:
                return False
            self.last_seen_at = self.clock()
            return True

    def release(self, client_ip: str, *, busy: bool) -> bool:
        with self.lock:
            if self.owner_ip != client_ip or busy:
                return False
            self._clear()
            return True

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return self._snapshot()

    def _assign(self, client_ip: str, entry: str, now: float) -> None:
        self.owner_ip = client_ip
        self.entry = entry
        self.acquired_at = now
        self.last_seen_at = now

    def _clear(self) -> None:
        self.owner_ip = ""
        self.entry = ""
        self.acquired_at = 0.0
        self.last_seen_at = 0.0

    def _snapshot(self) -> dict[str, object]:
        return {
            "occupied": bool(self.owner_ip),
            "ownerIp": self.owner_ip,
            "entry": self.entry,
            "acquiredAt": self.acquired_at,
            "lastSeenAt": self.last_seen_at,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
        }
