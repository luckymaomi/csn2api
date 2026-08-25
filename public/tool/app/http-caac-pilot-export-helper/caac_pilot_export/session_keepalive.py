from __future__ import annotations

import random
from datetime import datetime
from threading import Event, Lock, Thread, current_thread
from typing import Callable


def random_keepalive_interval() -> int:
    return random.randint(30, 60)


class SessionKeepAlive:
    def __init__(self, interval_factory: Callable[[], int], timeout_seconds: int, thread_name: str) -> None:
        self.interval_factory = interval_factory
        self.timeout_seconds = timeout_seconds
        self.thread_name = thread_name
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self.state = "stopped"
        self.last_checked_at = ""
        self.next_interval_seconds = 0
        self.error = ""

    def start(self, check: Callable[[], None], expired_matcher: Callable[[Exception], bool], on_expired: Callable[[], None]) -> None:
        self._stop_event = Event()
        self._thread = Thread(target=self._run, args=(check, expired_matcher, on_expired), name=self.thread_name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not current_thread():
            self._thread.join(timeout=self.timeout_seconds + 1)
        self._thread = None
        with self._lock:
            self.state, self.next_interval_seconds, self.error = "stopped", 0, ""

    def record_success(self) -> None:
        with self._lock:
            self.state, self.last_checked_at, self.error = "healthy", datetime.now().isoformat(timespec="seconds"), ""

    def status(self, ready: bool) -> dict[str, object]:
        with self._lock:
            return {"state": self.state, "running": bool(ready and self._thread and self._thread.is_alive()), "lastCheckedAt": self.last_checked_at, "nextIntervalSeconds": self.next_interval_seconds, "error": self.error}

    def _run(self, check: Callable[[], None], expired_matcher: Callable[[Exception], bool], on_expired: Callable[[], None]) -> None:
        while not self._stop_event.is_set():
            interval = max(1, int(self.interval_factory()))
            with self._lock:
                self.next_interval_seconds = interval
            if self._stop_event.wait(interval):
                break
            try:
                check()
            except Exception as error:
                if expired_matcher(error):
                    with self._lock:
                        self.state, self.error = "expired", str(error)
                    on_expired()
                    break
                with self._lock:
                    self.state, self.error, self.last_checked_at = "error", str(error), datetime.now().isoformat(timespec="seconds")
            else:
                self.record_success()
