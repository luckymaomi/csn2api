from __future__ import annotations

import signal
from types import FrameType


def _raise_keyboard_interrupt(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def install_interrupt_handlers() -> None:
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _raise_keyboard_interrupt)


__all__ = ["install_interrupt_handlers"]
