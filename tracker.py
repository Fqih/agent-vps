"""Job application tracker stored in state.sqlite."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from html import escape

from tg import button

FOLLOW_UP = timedelta(days=7)
ACTIVE = ("disimpan", "dilamar", "interview")
LIKED = ("disimpan", "dilamar", "interview", "offer", "ditolak")  # ditolak = rejected by them, still my pick
LABEL = {"baru": "Baru", "disimpan": "Disimpan", "dilamar": "Dilamar", "interview": "Interview",
         "ditolak": "Ditolak", "offer": "Offer", "batal": "Batal"}
NEXT = {
    "baru": [("Simpan", "disimpan"), ("Sudah lamar", "dilamar")],
    "disimpan": [("Sudah lamar", "dilamar"), ("Batal", "batal")],
    "dilamar": [("Interview", "interview"), ("Ditolak", "ditolak"), ("Sudah follow-up", "followup")],
    "interview": [("Offer", "offer"), ("Ditolak", "ditolak"), ("Sudah follow-up", "followup")],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT, company TEXT,
            location TEXT, source TEXT, status TEXT NOT NULL DEFAULT 'baru',
            created_at TEXT NOT NULL, applied_at TEXT, next_remind TEXT);
        CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
    """)
    try:  # digest and infobot both migrate; whoever is second sees the column already there
        db.execute("ALTER TABLE jobs ADD COLUMN feedback INTEGER")  # -1 = thumbs down on the digest
        db.commit()
    except sqlite3.OperationalError as err:
        if "duplicate column" not in str(err):
            raise


def record(db: sqlite3.Connection, job: dict, status: str = "baru") -> int:
    db.execute("INSERT OR IGNORE INTO jobs (url, title, company, location, source, status, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)",
               (job["url"], job.get("title", ""), job.get("company", ""), job.get("location", ""),
                job.get("source", ""), status, now_iso()))
    db.commit()
    return db.execute("SELECT id FROM jobs WHERE url = ?", (job["url"],)).fetchone()[0]


def get(db: sqlite3.Connection, job_id: int) -> dict | None:
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    db.row_factory = None
    return dict(row) if row else None


def set_status(db: sqlite3.Connection, job_id: int, action: str, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    job = get(db, job_id)
    if job is None or action not in {a for opts in NEXT.values() for _, a in opts}:
        return None
    remind = (now + FOLLOW_UP).isoformat()
    if action == "followup":
        db.execute("UPDATE jobs SET next_remind = ? WHERE id = ?", (remind, job_id))
    elif action == "dilamar":
        db.execute("UPDATE jobs SET status = ?, applied_at = ?, next_remind = ? WHERE id = ?",
                   (action, now.isoformat(), remind, job_id))
    elif action == "interview":
        db.execute("UPDATE jobs SET status = ?, next_remind = ? WHERE id = ?", (action, remind, job_id))
    else:
        db.execute("UPDATE jobs SET status = ?, next_remind = NULL WHERE id = ?", (action, job_id))
    db.commit()
    return get(db, job_id)


def card(job: dict) -> tuple[str, list]:
    text = (f'<b>{escape(job["title"] or "?")}</b> | {escape(job["company"] or "?")}\n'
            f'{escape(job["location"] or "")}\n<a href="{escape(job["url"])}">Buka lowongan</a>\n'
            f'Status: <b>{LABEL[job["status"]]}</b>'
            + (f' (lamar {job["applied_at"][:10]})' if job.get("applied_at") else ""))
    buttons = [[button(label, f"st:{job['id']}:{action}") for label, action in NEXT.get(job["status"], [])]]
    return text, [row for row in buttons if row]


def active_list(db: sqlite3.Connection) -> str:
    rows = db.execute(f"SELECT id, title, company, status FROM jobs WHERE status IN "
                      f"({','.join('?' * len(ACTIVE))}) ORDER BY status, id DESC", ACTIVE).fetchall()
    if not rows:
        return "Belum ada lamaran aktif. Simpan dari digest pagi atau /tambah &lt;url&gt; &lt;judul&gt;."
    lines, current = ["<b>Lamaran aktif</b>"], None
    for jid, title, company, status in rows:
        if status != current:
            lines.append(f"\n<b>{LABEL[status]}</b>")
            current = status
        lines.append(f"/j{jid} {escape(title or '?')} | {escape(company or '?')}")
    return "\n".join(lines)


def due_reminders(db: sqlite3.Connection, now: datetime) -> list[dict]:
    ids = [r[0] for r in db.execute(
        "SELECT id FROM jobs WHERE status IN ('dilamar', 'interview') AND next_remind <= ?",
        (now.isoformat(),))]
    for jid in ids:  # push the next reminder out so it fires once per week, not every tick
        db.execute("UPDATE jobs SET next_remind = ? WHERE id = ?", ((now + FOLLOW_UP).isoformat(), jid))
    db.commit()
    return [get(db, jid) for jid in ids]


def set_feedback(db: sqlite3.Connection, job_id: int, value: int) -> bool:
    cur = db.execute("UPDATE jobs SET feedback = ? WHERE id = ?", (value, job_id))
    db.commit()
    return cur.rowcount > 0


def preferences(db: sqlite3.Connection, limit: int = 15) -> str:
    """Recent picks and rejects, fed to the ranking prompt as taste examples."""
    marks = ",".join("?" * len(LIKED))
    liked = db.execute(f"SELECT title, company FROM jobs WHERE status IN ({marks}) "
                       "ORDER BY id DESC LIMIT ?", (*LIKED, limit)).fetchall()
    disliked = db.execute("SELECT title, company FROM jobs WHERE feedback = -1 "
                          "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    parts = [f"{label}:\n" + "\n".join(f"- {t} @ {c}" for t, c in rows)
             for label, rows in (("Disukai", liked), ("Tidak cocok", disliked)) if rows]
    return "\n".join(parts)


def recap(db: sqlite3.Connection, now: datetime) -> str:
    week_ago = (now - timedelta(days=7)).isoformat()
    counts = dict(db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())
    applied_week = db.execute("SELECT COUNT(*) FROM jobs WHERE applied_at >= ?", (week_ago,)).fetchone()[0]
    parts = [f"{LABEL[s]}: {counts.get(s, 0)}" for s in ("disimpan", "dilamar", "interview", "offer", "ditolak")]
    sent, used, bad = db.execute("SELECT COUNT(*), SUM(status != 'baru'), SUM(feedback = -1) FROM jobs "
                                 "WHERE created_at >= ?", (week_ago,)).fetchone()
    quality = f"Kualitas digest: {sent} lowongan dikirim: {used or 0} dipakai, {bad or 0} tidak cocok\n" if sent else ""
    return (f"<b>Rekap lamaran</b>\nMinggu ini dilamar: <b>{applied_week}</b>\n" + "\n".join(parts)
            + f"\n\n{quality}/lamaran untuk detail")


def kv_get(db: sqlite3.Connection, key: str, default: str = "") -> str:
    row = db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def kv_set(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, value))
    db.commit()
