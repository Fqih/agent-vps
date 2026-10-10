"""Read-later: send a link to the info bot, get a 3-point summary, weekly recap."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from html import escape

import sources
from digest import chat_json
from tg import button

URL = re.compile(r"https?://\S+")
PAGE_CHARS = 8000


def init(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS reads (
        id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT, summary TEXT,
        created_at TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)""")
    db.commit()


def first_url(text: str) -> str | None:
    m = URL.search(text or "")
    return m.group(0).rstrip(").,>") if m else None


def fetch(url: str) -> tuple[str, str]:
    try:
        page = sources.get(url).decode("utf-8", "replace")
    except Exception:
        return "", ""
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    return sources.strip_tags(title.group(1), 160) if title else "", sources.strip_tags(body, PAGE_CHARS)


def summarize(url: str, cfg: dict) -> tuple[str, str]:
    title, body = fetch(url)
    if not body:
        return title or url, "(isi halaman tidak bisa diambil, mungkin diblokir atau butuh login)"
    out = chat_json(f"""Ringkas artikel ini dalam Bahasa Indonesia.
Judul: {title}
Isi: {body}
Balas HANYA JSON: {{"title": "judul singkat", "points": ["poin 1", "poin 2", "poin 3"]}}
Tiap poin maksimal 25 kata, fokus pada hal yang bisa dipakai/diingat.""", cfg)
    points = [str(p) for p in out.get("points", [])][:3]
    return str(out.get("title") or title or url)[:160], "\n".join(f"- {p}" for p in points)


def save(db: sqlite3.Connection, url: str, title: str, summary: str) -> int:
    db.execute("INSERT OR REPLACE INTO reads (url, title, summary, created_at, done) VALUES (?, ?, ?, ?, 0)",
               (url, title, summary, datetime.now(timezone.utc).isoformat()))
    db.commit()
    return db.execute("SELECT id FROM reads WHERE url = ?", (url,)).fetchone()[0]


def card(rid: int, url: str, title: str, summary: str) -> tuple[str, list]:
    text = f'<b>{escape(title)}</b>\n{escape(summary)}\n<a href="{escape(url)}">Buka</a>'
    return text, [[button("Sudah dibaca", f"rd:{rid}")]]


def mark_done(db: sqlite3.Connection, rid: int) -> bool:
    cur = db.execute("UPDATE reads SET done = 1 WHERE id = ?", (rid,))
    db.commit()
    return cur.rowcount > 0


def unread(db: sqlite3.Connection, limit: int = 15) -> str:
    rows = db.execute("SELECT url, title FROM reads WHERE done = 0 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return "Tidak ada bacaan tertunda. Kirim link apa saja untuk disimpan."
    return "<b>Belum dibaca</b>\n" + "\n".join(
        f'- <a href="{escape(u)}">{escape(t or u)}</a>' for u, t in rows)


def weekly_recap(db: sqlite3.Connection, now: datetime) -> str | None:
    since = (now - timedelta(days=7)).isoformat()
    rows = db.execute("SELECT url, title, done FROM reads WHERE created_at >= ? ORDER BY done, id",
                      (since,)).fetchall()
    if not rows:
        return None
    pending = sum(1 for *_, d in rows if not d)
    lines = [f"<b>Rekap bacaan minggu ini</b> ({len(rows)} disimpan, {pending} belum dibaca)"]
    lines += [f'{"[x]" if d else "[ ]"} <a href="{escape(u)}">{escape(t or u)}</a>' for u, t, d in rows]
    return "\n".join(lines)
