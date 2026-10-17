"""Helpers shared by the status collectors."""
from __future__ import annotations

import sqlite3
import threading
from datetime import timedelta, timezone

WIB = timezone(timedelta(hours=7))


def ro(path) -> sqlite3.Connection:
    """Read-only connection: collectors must never write to another service's DB."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)


def every(name: str, seconds: int, fn) -> threading.Thread:
    """Run fn now and then every `seconds` in a daemon thread; fn must not raise."""
    def loop():
        while True:
            fn()
            threading.Event().wait(seconds)
    thread = threading.Thread(target=loop, name=name, daemon=True)
    thread.start()
    return thread
