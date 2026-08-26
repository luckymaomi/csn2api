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
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._expired_matcher: Callable[[Exception], bool] | None = None
        self._on_expired: Callable[[], None] | None = None
        self.state = "stopped"
        self.last_checked_at = ""
        self.next_interval_seconds = 0
        self.error = ""

    def start(self, check: Callable[[], None], expired_matcher: Callable[[Exception], bool], on_expired: Callable[[], None]) -> None:
        self._stop_event = Event()
        self._expired_matcher = expired_matcher
        self._on_expired = on_expired
        self._thread = Thread(target=self._run, args=(check,), name=self.thread_name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not current_thread():
            thread.join(timeout=self.timeout_seconds + 1)
        with self._lock:
            self._thread = None
            self.state = "stopped"
            self.next_interval_seconds = 0
            self.error = ""

    def record_success(self) -> None:
        with self._lock:
            self.state = "healthy"
            self.error = ""
            self.last_checked_at = self._now()

    def mark_expired(self) -> None:
        self._stop_event.set()
        with self._lock:
            self.state = "expired"
            self.last_checked_at = self._now()
            self.next_interval_seconds = 0
            self.error = ""

    def status(self, ready: bool) -> dict[str, object]:
        with self._lock:
            return {
                "state": self.state,
                "running": bool(ready and self.state != "expired" and self._thread is not None and self._thread.is_alive()),
                "lastCheckedAt": self.last_checked_at,
                "nextIntervalSeconds": self.next_interval_seconds,
                "error": self.error,
            }

    def _run(self, check: Callable[[], None]) -> None:
        while not self._stop_event.is_set():
            try:
                interval = max(1, int(self.interval_factory()))
            except Exception as error:
                interval = 30
                with self._lock:
                    self.state = "error"
                    self.error = f"保活间隔生成失败：{error}"
            with self._lock:
                self.next_interval_seconds = interval
            if self._stop_event.wait(interval):
                break
            with self._lock:
                self.state = "checking"
            try:
                check()
            except Exception as error:
                if self._expired_matcher is not None and self._expired_matcher(error):
                    self.mark_expired()
                    if self._on_expired is not None:
                        self._on_expired()
                    break
                with self._lock:
                    self.state = "error"
                    self.error = str(error) or error.__class__.__name__
                    self.last_checked_at = self._now()
            else:
                self.record_success()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

