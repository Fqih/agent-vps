"""VPS samples (cpu/ram/disk %) for the widget line charts, kept 24 h in state.sqlite."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

KEEP = timedelta(hours=24)
FIELDS = ("cpu", "ram", "disk")


def init(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE IF NOT EXISTS vps_samples (ts TEXT PRIMARY KEY, cpu INTEGER, ram INTEGER, disk INTEGER)")


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat(timespec="seconds")


def record(db: sqlite3.Connection, ts: datetime, cpu: int, ram: int, disk: int) -> None:
    init(db)
    with db:
        db.execute("INSERT OR REPLACE INTO vps_samples VALUES (?, ?, ?, ?)", (_iso(ts), cpu, ram, disk))
        db.execute("DELETE FROM vps_samples WHERE ts < ?", (_iso(ts - KEEP),))


def series(db: sqlite3.Connection, now: datetime, hours: int = 6, points: int = 36) -> dict:
    """Oldest-first values per field over the window, evenly thinned to at most `points`."""
    try:
        rows = db.execute("SELECT cpu, ram, disk FROM vps_samples WHERE ts >= ? ORDER BY ts",
                          (_iso(now - timedelta(hours=hours)),)).fetchall()
    except sqlite3.OperationalError:  # infobot has not recorded anything yet
        rows = []
    if len(rows) > points:
        rows = [rows[i * (len(rows) - 1) // (points - 1)] for i in range(points)]
    return {name: [r[i] for r in rows] for i, name in enumerate(FIELDS)}
