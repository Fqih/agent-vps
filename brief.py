"""Company + interview brief for a job the owner applied to."""
from __future__ import annotations

from html import escape

import sources
from digest import PROFILE, chat_text

PAGE_CHARS = 6000


def job_page_text(url: str) -> str:
    """Best effort: many job boards block bots, the brief still works from title/company."""
    try:
        return sources.strip_tags(sources.get(url).decode("utf-8", "replace"), PAGE_CHARS)
    except Exception:
        return ""


def build_prompt(job: dict, stage: str, page: str) -> str:
    focus = ("Fokus persiapan INTERVIEW: pertanyaan teknis & behavioral yang paling mungkin, plus cara menjawab."
             if stage == "interview" else
             "Fokus riset awal setelah melamar: apa yang perlu diketahui dan disiapkan.")
    return f"""Kamu career coach untuk kandidat ini:
{PROFILE}

Lowongan: {job.get('title')} di {job.get('company')} ({job.get('location') or '-'})
Link: {job.get('url')}
Isi halaman lowongan (bisa kosong/terpotong):
{page or '(tidak tersedia)'}

{focus}
Tulis dalam Bahasa Indonesia, teks polos tanpa markdown/tabel, maksimal 250 kata, dengan bagian:
PERUSAHAAN: 2-3 kalimat (bisnis, produk). Jika tidak yakin, katakan tidak yakin; jangan mengarang fakta.
KEMUNGKINAN STACK: 1 baris.
5 PERTANYAAN INTERVIEW: tiap pertanyaan + 1 kalimat cara menjawab memakai pengalaman kandidat.
PERTANYAAN BALIK: 2 pertanyaan cerdas untuk interviewer."""


def generate(job: dict, stage: str, cfg: dict) -> str:
    text = chat_text(build_prompt(job, stage, job_page_text(job["url"])), cfg)
    title = "Persiapan interview" if stage == "interview" else "Brief perusahaan"
    return f"<b>{title}: {escape(job.get('company') or '?')}</b>\n{escape(text)}"
