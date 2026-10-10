"""Daily interview practice with spaced repetition."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from html import escape

from digest import PROFILE, chat_json

TOPICS = ["machine learning fundamentals", "statistik & probabilitas", "SQL", "Python & struktur data",
          "LLM, RAG & agent system design", "deep learning & computer vision", "NLP",
          "MLOps & deployment", "behavioral (STAR)"]


def init(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY, topic TEXT, question TEXT NOT NULL, ideal TEXT,
        score INTEGER, due TEXT, created_at TEXT NOT NULL)""")
    db.commit()


def next_due(score: int, now: datetime) -> str:
    days = 14 if score >= 8 else 3 if score >= 5 else 1
    return (now + timedelta(days=days)).isoformat()


def due_question(db: sqlite3.Connection, now: datetime) -> tuple | None:
    return db.execute("SELECT id, topic, question FROM questions WHERE score < 8 AND due <= ? "
                      "ORDER BY due LIMIT 1", (now.isoformat(),)).fetchone()


def new_question(db: sqlite3.Connection, cfg: dict) -> tuple:
    count = db.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    topic = TOPICS[count % len(TOPICS)]
    recent = [r[0] for r in db.execute("SELECT question FROM questions ORDER BY id DESC LIMIT 25")]
    out = chat_json(f"""Buat 1 soal interview kerja level entry-mid untuk kandidat ini:
{PROFILE}
Topik: {topic}. Soal harus bisa dijawab dalam 3-6 kalimat, realistis seperti di interview AI/Data Indonesia.
Jangan mengulang soal ini: {recent}
Balas HANYA JSON: {{"question": "...", "ideal": "jawaban ideal ringkas, maks 80 kata"}}""", cfg)
    if not out.get("question"):
        raise ValueError("LLM tidak memberi soal")
    cur = db.execute("INSERT INTO questions (topic, question, ideal, created_at) VALUES (?, ?, ?, ?)",
                     (topic, out["question"], out.get("ideal", ""), datetime.now(timezone.utc).isoformat()))
    db.commit()
    return cur.lastrowid, topic, out["question"]


def ask(db: sqlite3.Connection, cfg: dict, now: datetime) -> tuple[int, str]:
    q = due_question(db, now)
    repeat = q is not None
    qid, topic, question = q if repeat else new_question(db, cfg)
    label = "Ulangan" if repeat else "Soal baru"
    return qid, (f"<b>Latihan interview</b> ({label}, {escape(topic)})\n{escape(question)}\n\n"
                 "<i>Balas pesan ini dengan jawabanmu. /skip untuk lewati.</i>")


def grade(db: sqlite3.Connection, qid: int, answer: str, cfg: dict, now: datetime) -> str:
    topic, question, ideal = db.execute("SELECT topic, question, ideal FROM questions WHERE id = ?",
                                        (qid,)).fetchone()
    out = chat_json(f"""Nilai jawaban interview ini secara jujur dan spesifik.
Soal ({topic}): {question}
Jawaban ideal referensi: {ideal}
Jawaban kandidat: {answer}
Balas HANYA JSON: {{"score": 0-10, "feedback": "apa yang kurang/salah, maks 60 kata"}}""", cfg)
    score = max(0, min(10, int(out.get("score", 0))))
    db.execute("UPDATE questions SET score = ?, due = ? WHERE id = ?", (score, next_due(score, now), qid))
    db.commit()
    again = "diulang besok" if score < 5 else "diulang 3 hari lagi" if score < 8 else "lulus, cek lagi 2 minggu"
    return (f"<b>Skor {score}/10</b> ({again})\n{escape(str(out.get('feedback', '')))}\n\n"
            f"<b>Jawaban ideal:</b>\n{escape(ideal or '-')}")
