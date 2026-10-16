"""Helpers shared by the status collectors."""
from __future__ import annotations

import sqlite3
from datetime import timedelta, timezone

WIB = timezone(timedelta(hours=7))


def ro(path) -> sqlite3.Connection:
    """Read-only connection: collectors must never write to another service's DB."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
