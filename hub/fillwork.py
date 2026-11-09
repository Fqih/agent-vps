"""Handlers for the tasks hub.filler queues. Each returns (text, model)."""
from __future__ import annotations

import re
import sqlite3
import urllib.request
from contextlib import closing
from datetime import datetime, timezone

import brief
import practice
import readlater
from digest import PROFILE, _parse_json
from hub import llm

DIFF_CHARS = 15000


def _ask(task: dict, ctx: dict, prompt: str) -> tuple:
    return llm.chat(task["chain"], [{"role": "user", "content": prompt}], ctx.get("cfg", {}))


def job(task: dict, ctx: dict) -> tuple:
    p = task["payload"]
    page = brief.job_page_text(p["url"])
    text, model = _ask(task, ctx, f"""Kamu career coach. Profil kandidat (satu-satunya sumber fakta tentang kandidat):
{PROFILE}

Lowongan: {p.get('job_title')} di {p.get('company')} ({p.get('location') or '-'})
Link: {p['url']}
Isi halaman lowongan (bisa kosong/terpotong):
{page or '(tidak tersedia)'}

Nilai kecocokan kandidat dengan lowongan ini. Jangan mengarang pengalaman, angka, atau skill yang
tidak ada di profil; skill yang diminta tapi tidak dimiliki masuk ke "gap".
Balas HANYA JSON:
{{"score": 0-100, "alasan": "2 kalimat", "gap": "skill/syarat yang kurang, atau '-'",
"perusahaan": "2 kalimat tentang perusahaan; tulis 'tidak yakin' jika tidak tahu",
"cover_letter": "draft cover letter Bahasa Indonesia maks 150 kata, hanya fakta dari profil"}}""")
    out = _parse_json(text)
    m = re.search(r"\d+", str(out.get("score", "")))  # tolerate "85/100" or "85.5"
    if not m:
        raise ValueError("LLM tidak memberi skor")
    score = max(0, min(100, int(m.group())))
    return (f"Skor: {score}/100\n{p.get('job_title')} @ {p.get('company')}\n{p['url']}\n\n"
            f"Alasan: {out.get('alasan', '-')}\nGap: {out.get('gap', '-')}\n"
            f"Perusahaan: {out.get('perusahaan', '-')}\n\nDraft cover letter:\n{out.get('cover_letter', '-')}"), model


def fetch_diff(repo: str, sha: str) -> str:
    req = urllib.request.Request(f"https://github.com/{repo}/commit/{sha}.diff", headers={"User-Agent": "hub-filler"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read(DIFF_CHARS).decode("utf-8", "replace")


def review(task: dict, ctx: dict) -> tuple:
    p = task["payload"]
    diff = fetch_diff(p["repo"], p["sha"])
    return _ask(task, ctx, f"""Review commit ini dari repo {p['repo']} ({p['sha'][:7]}) seperti senior engineer.
Cari: bug, masalah keamanan (secret, injection), error handling yang hilang, kode yang bisa jauh lebih sederhana.
Abaikan gaya/format. Tiap temuan satu baris: file:baris - masalah - saran perbaikan.
Jika tidak ada yang penting, jawab persis "Tidak ada temuan." Bahasa Indonesia, teks polos, maks 200 kata.
Diff (bisa terpotong):
{diff}""")


def read(task: dict, ctx: dict) -> tuple:
    p = task["payload"]
    title, body = readlater.fetch(p["url"])
    if not body:
        raise ValueError("isi halaman tidak bisa diambil")
    return _ask(task, ctx, f"""Buat ringkasan mendalam artikel ini dalam Bahasa Indonesia, teks polos tanpa markdown.
Judul: {title}
Isi: {body}
Bagian: INTI (3-5 kalimat), POIN PENTING (5 poin), YANG BISA DIPAKAI (2-3 hal praktis untuk AI/data engineer),
3 PERTANYAAN LATIHAN tentang isi artikel beserta jawaban singkat. Maks 350 kata.""")


def question(task: dict, ctx: dict) -> tuple:
    topic = task["payload"]["topic"]
    with closing(sqlite3.connect(str(ctx["state_db"]), timeout=30)) as db:
        recent = [r[0] for r in db.execute("SELECT question FROM questions ORDER BY id DESC LIMIT 25")]
    text, model = _ask(task, ctx, f"""Buat 1 soal interview kerja level entry-mid untuk kandidat ini:
{PROFILE}
Topik: {topic}. Soal harus bisa dijawab dalam 3-6 kalimat, realistis seperti di interview AI/Data Indonesia.
Jangan mengulang soal ini: {recent}
Balas HANYA JSON: {{"question": "...", "ideal": "jawaban ideal ringkas, maks 80 kata"}}""")
    out = _parse_json(text)
    if not out.get("question"):
        raise ValueError("LLM tidak memberi soal")
    with closing(sqlite3.connect(str(ctx["state_db"]), timeout=30)) as db:
        practice.init(db)  # adds the source column if infobot has not migrated yet
        db.execute("INSERT INTO questions (topic, question, ideal, source, created_at) VALUES (?, ?, ?, 'bank', ?)",
                   (topic, out["question"], out.get("ideal", ""), datetime.now(timezone.utc).isoformat()))
        db.commit()
    return f"{topic}: {out['question']}", model
