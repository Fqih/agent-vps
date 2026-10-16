"""Task queue in its own SQLite file so long LLM work never locks state.sqlite."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "tasks.sqlite"
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))
SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    chain TEXT NOT NULL DEFAULT 'fast',
    dedup_key TEXT UNIQUE,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    run_after TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    model TEXT,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_ready ON tasks (status, run_after);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def connect(path=DB_PATH) -> sqlite3.Connection:
    # prompts and results live here: owner-only; SQLite gives -wal/-shm the main file's mode
    if str(path) != ":memory:":
        Path(path).touch(mode=0o600, exist_ok=True)
        for f in (Path(path), Path(f"{path}-wal"), Path(f"{path}-shm")):
            if f.exists():
                os.chmod(f, 0o600)
    db = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def enqueue(db: sqlite3.Connection, kind: str, payload: dict, chain: str = "fast",
            dedup_key: str | None = None, now: datetime | None = None) -> int:
    if dedup_key:
        row = db.execute("SELECT id FROM tasks WHERE dedup_key = ?", (dedup_key,)).fetchone()
        if row:
            return row["id"]
    stamp = iso(now or utcnow())
    cur = db.execute(
        "INSERT INTO tasks (kind, payload, chain, dedup_key, status, run_after, created_at) "
        "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
        (kind, json.dumps(payload, ensure_ascii=False), chain, dedup_key, stamp, stamp))
    db.commit()
    return cur.lastrowid


def get(db: sqlite3.Connection, task_id: int) -> dict | None:
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    task = dict(row)
    task["payload"] = json.loads(task["payload"])
    return task


def claim(db: sqlite3.Connection, now: datetime | None = None) -> dict | None:
    stamp = iso(now or utcnow())
    row = db.execute("SELECT id FROM tasks WHERE status = 'queued' AND run_after <= ? "
                     "ORDER BY run_after, id LIMIT 1", (stamp,)).fetchone()
    if row is None:
        return None
    db.execute("UPDATE tasks SET status = 'running', started_at = ? WHERE id = ?", (stamp, row["id"]))
    db.commit()
    return get(db, row["id"])


def finish(db: sqlite3.Connection, task_id: int, result: str, model: str, now: datetime | None = None) -> None:
    db.execute("UPDATE tasks SET status = 'done', result = ?, model = ?, error = NULL, finished_at = ? "
               "WHERE id = ?", (result, model, iso(now or utcnow()), task_id))
    db.commit()


def fail_now(db: sqlite3.Connection, task_id: int, error: str, now: datetime | None = None) -> None:
    db.execute("UPDATE tasks SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
               (error[:500], iso(now or utcnow()), task_id))
    db.commit()


def retry_or_fail(db: sqlite3.Connection, task_id: int, error: str, now: datetime | None = None) -> str:
    now = now or utcnow()
    attempts = db.execute("SELECT attempts FROM tasks WHERE id = ?", (task_id,)).fetchone()["attempts"] + 1
    if attempts > len(RETRY_DELAYS):
        db.execute("UPDATE tasks SET status = 'failed', attempts = ?, error = ?, finished_at = ? WHERE id = ?",
                   (attempts, error[:500], iso(now), task_id))
        db.commit()
        return "failed"
    db.execute("UPDATE tasks SET status = 'queued', attempts = ?, error = ?, run_after = ?, started_at = NULL "
               "WHERE id = ?", (attempts, error[:500], iso(now + RETRY_DELAYS[attempts - 1]), task_id))
    db.commit()
    return "queued"


def requeue_running(db: sqlite3.Connection) -> int:
    """Single worker: anything still 'running' at start-up was orphaned by a crash."""
    cur = db.execute("UPDATE tasks SET status = 'queued', started_at = NULL WHERE status = 'running'")
    db.commit()
    return cur.rowcount


def counts(db: sqlite3.Connection, now: datetime | None = None) -> dict:
    now = now or utcnow()
    live = {status: n for status, n in db.execute(
        "SELECT status, COUNT(*) FROM tasks WHERE status IN ('queued', 'running') GROUP BY status")}
    failed = db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'failed' AND finished_at >= ?",
                        (iso(now - timedelta(days=1)),)).fetchone()[0]
    return {"running": live.get("running", 0), "queued": live.get("queued", 0), "failed": failed}


def recent(db: sqlite3.Connection, limit: int = 20) -> list:
    rows = db.execute(
        "SELECT id, kind, status, model, created_at, finished_at, payload, "
        "substr(coalesce(result, ''), 1, 200) AS preview, error FROM tasks ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for row in rows:
        item = dict(row)
        item["title"] = json.loads(item.pop("payload")).get("title") or item["kind"]
        out.append(item)
    return out
