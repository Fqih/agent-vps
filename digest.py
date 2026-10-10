#!/usr/bin/env python3
"""Hermes digest: short daily news + fresh entry-mid AI/data jobs to Telegram.

Data comes from feeds that carry a real posting date, gets filtered in code
(age, seniority, location, already-sent), and the LLM only ranks and summarizes.

    python3 digest.py            # daily digest
    python3 digest.py --weekly   # Big 4 / BUMN scan via hermes agent
    python3 digest.py --dry-run  # print instead of sending, do not mark as seen
"""
from __future__ import annotations

import fcntl
import html
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import filters
import sources
import tg
import tracker

HOME = Path.home()
HERE = Path(__file__).resolve().parent
REPORT_DIR = HOME / "hermes_reports"
DB_PATH = HERE / "state.sqlite"
HERMES_CONFIG = HOME / ".hermes" / "config.yaml"
ENV_FILES = [HOME / ".hermes" / "hermes.env", HOME / ".hermes" / ".env"]
WIB = timezone(timedelta(hours=7))

FALLBACK_MODELS = [m for m in os.environ.get("DIGEST_FALLBACK_MODELS", "ag/gemini-3.7-flash-high,gh/gpt-4.1-2025-04-14").split(",") if m]
WEEKLY_MODELS = os.environ.get("DIGEST_WEEKLY_MODELS", "ag/gemini-3.1-pro-low,cc/claude-sonnet-5").split(",")
MAX_JOBS = 5
MAX_NEWS = 3
TG_LIMIT = 3900
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

PROFILE = """Fresh graduate S1 Informatika (Agustus 2026), IPK 3.88, Jakarta/Depok.
Target: AI Engineer, ML Engineer, Data Scientist, Data Analyst. Level entry sampai mid (0-3 tahun).
Lokasi: Jakarta (onsite/hybrid) atau remote.
Skill: Python, PyTorch, LLM & agentic AI (LangChain, LangGraph, ReAct), RAG (Qdrant, BM25, RRF),
vLLM & serving model lokal (Qwen), fine-tuning, Graph ML/GNN (GAT), computer vision (YOLO),
NLP/sentiment (BiLSTM, IndoBERT), SQL/PostgreSQL, Docker, NVIDIA DGX A100.
Pengalaman: magang AI Engineer (dokumen/OCR, rekonsiliasi pajak), research assistant ML, asisten HPC."""

log = logging.getLogger("digest")


# ---------- config / secrets ----------

def load_env() -> dict:
    env = dict(os.environ)
    for path in ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
            if m and not line.lstrip().startswith("#"):
                env.setdefault(m.group(1), m.group(2).strip().strip("'\""))
    return env


def model_config(env: dict) -> dict:
    """Read the `model:` block of hermes config.yaml (flat keys only)."""
    cfg, inside = {}, False
    for line in HERMES_CONFIG.read_text().splitlines():
        if re.match(r"^model:\s*$", line):
            inside = True
            continue
        if inside and re.match(r"^\S", line):
            break
        m = re.match(r"^\s+(\w+):\s*\"?([^\"#]*?)\"?\s*$", line) if inside else None
        if m:
            cfg[m.group(1)] = re.sub(r"\$\{(\w+)\}", lambda v: env.get(v.group(1), ""), m.group(2))
    return cfg


# ---------- LLM ----------

def _complete(model: str, prompt: str, cfg: dict) -> str:
    url = cfg.get("base_url", "http://127.0.0.1:20128/v1").rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "stream": False,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {cfg.get('api_key', '')}",
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)["choices"][0]["message"]["content"]
    except (KeyError, ValueError):
        log.warning("response %s tidak terduga: %.300s", model, raw)
        raise


def _with_fallback(prompt: str, cfg: dict, parse):
    last_err = None
    for model in filter(None, [cfg.get("default", "")] + FALLBACK_MODELS):
        try:
            return parse(_complete(model, prompt, cfg))
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as err:
            last_err = err
            log.warning("LLM %s gagal: %s", model, err)
    raise RuntimeError(f"semua model gagal: {last_err}")


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0)) if match else {}


def chat_json(prompt: str, cfg: dict) -> dict:
    return _with_fallback(prompt, cfg, _parse_json)


def chat_text(prompt: str, cfg: dict) -> str:
    return _with_fallback(prompt, cfg, str.strip)


def brief(items: list[dict], fields: tuple) -> str:
    return json.dumps([{"i": i, **{f: it.get(f) for f in fields}} for i, it in enumerate(items)],
                      ensure_ascii=False)


def pick(llm_out: dict, key: str, items: list[dict], extra: str, limit: int) -> list[dict]:
    chosen = []
    for p in llm_out.get(key, [])[:limit]:
        i = p.get("i") if isinstance(p, dict) else None
        if isinstance(i, int) and 0 <= i < len(items):
            chosen.append({**items[i], extra: str(p.get(extra, ""))[:200]})
    return chosen


def rank_news(news_id: list[dict], news_tech: list[dict], cfg: dict) -> tuple:
    prompt = f"""Pilih berita paling penting dan berdampak (hindari seremonial/gosip/duplikat topik).
A = berita Indonesia (ekonomi/politik/bisnis), B = berita AI & tech global.
A: {brief(news_id, ("title", "source", "snippet"))}
B: {brief(news_tech, ("title", "source", "snippet"))}
Balas HANYA JSON: {{"id": [{{"i": 0, "summary": "..."}}], "tech": [...]}}
Maksimal {MAX_NEWS} per kelompok. summary = 1 kalimat Bahasa Indonesia, maksimal 20 kata."""
    out = chat_json(prompt, cfg)
    return (pick(out, "id", news_id, "summary", MAX_NEWS),
            pick(out, "tech", news_tech, "summary", MAX_NEWS))


def rank_jobs(jobs: list[dict], cfg: dict) -> list[dict]:
    prompt = f"""Kamu menyaring lowongan untuk kandidat ini:
{PROFILE}

Kandidat lowongan (sudah difilter: baru, bukan senior, lokasi cocok):
{brief(jobs, ("title", "company", "location", "source", "snippet"))}

Pilih maksimal {MAX_JOBS} yang PALING cocok dan realistis dilamar fresh grad (0-3 tahun).
Buang yang butuh pengalaman >3 tahun, bukan peran AI/data sungguhan, atau penyalur/spam.
Balas HANYA JSON: {{"jobs": [{{"i": 0, "why": "alasan cocok, maks 12 kata"}}]}}, urut dari paling cocok.
Boleh kosong jika tidak ada yang cocok."""
    return pick(chat_json(prompt, cfg), "jobs", jobs, "why", MAX_JOBS)


# ---------- state ----------

def open_db() -> sqlite3.Connection:
    # infobot shares this file: WAL lets its reads run during our writes, and the
    # commit below releases the write lock before the minute-long LLM ranking.
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
    db.execute("DELETE FROM seen WHERE sent_at < ?",
               ((datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),))
    db.commit()
    return db


def is_seen(db: sqlite3.Connection, keys: list[str]) -> bool:
    marks = ",".join("?" * len(keys))
    return db.execute(f"SELECT 1 FROM seen WHERE key IN ({marks}) LIMIT 1", keys).fetchone() is not None


def mark_seen(db: sqlite3.Connection, keys: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.executemany("INSERT OR REPLACE INTO seen VALUES (?, ?)", [(k, now) for k in keys])
    db.commit()


def link_alive(url: str) -> bool:
    """Only a hard 404/410 counts as dead; 403/429 from bot protection are kept."""
    req = urllib.request.Request(url, headers={"User-Agent": sources.UA})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return True
    except urllib.error.HTTPError as err:
        return err.code not in (404, 410)
    except (urllib.error.URLError, TimeoutError):
        return True


# ---------- telegram ----------

def telegram(method: str, env: dict, **params) -> dict:
    url = f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/{method}"
    data = urllib.parse.urlencode({"chat_id": env["TELEGRAM_CHAT_ID"], **params}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return json.loads(err.read() or b"{}")


def send(text: str, env: dict) -> bool:
    chunks, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > TG_LIMIT:
            chunks.append(buf)
            buf = ""
        buf += line
    chunks.append(buf)
    ok = True
    for chunk in filter(str.strip, chunks):
        resp = telegram("sendMessage", env, text=chunk, parse_mode="HTML", disable_web_page_preview="true")
        if not resp.get("ok"):
            log.warning("HTML ditolak (%s), kirim plain text", resp.get("description"))
            plain = re.sub(r'<a href="([^"]+)">([^<]*)</a>', r"\2 (\1)", chunk)
            plain = html.unescape(re.sub(r"</?[^>]+>", "", plain))
            ok = telegram("sendMessage", env, text=plain, disable_web_page_preview="true").get("ok", False) and ok
    return ok


def jobs_env(env: dict) -> dict:
    """Job lists and the tracker live on their own bot; fall back to the news bot if unset."""
    return {**env, "TELEGRAM_BOT_TOKEN": env.get("JOBS_BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN", "")}


def send_job_picker(db: sqlite3.Connection, env: dict, jobs: list[dict]) -> None:
    """One button per numbered job; infobot handles the taps."""
    if not jobs:
        return
    tracker.init(db)
    ids = [tracker.record(db, j) for j in jobs]
    buttons = [[tg.button(f"Simpan {n}", f"sv:{jid}") for n, jid in enumerate(ids, 1)]]
    tg.send(env, "Simpan lowongan ke tracker:", buttons)


def notify_error(env: dict, msg: str) -> None:
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        telegram("sendMessage", env, text=f"Hermes digest gagal: {msg}")


# ---------- runs ----------

def collect(fetchers: dict) -> tuple:
    items, failed = [], []
    for name, fn in fetchers.items():
        try:
            got = fn()
            log.info("%s: %d item", name, len(got))
            items += got
        except Exception as err:  # one broken source must not kill the digest
            log.warning("%s gagal: %s", name, err)
            failed.append(name)
    return items, failed


def daily(env: dict, cfg: dict, db: sqlite3.Connection, now: datetime, dry_run: bool) -> str:
    news = {}
    news_failed = []
    for group, feeds in sources.NEWS_FEEDS.items():
        got, bad = collect({f"{src} {url}": (lambda s=src, u=url: sources.rss(s, u)) for src, url in feeds})
        fresh = [n for n in got if filters.is_fresh_news(n, now) and not is_seen(db, [filters.url_key(n["url"])])]
        news[group] = filters.dedupe(sorted(fresh, key=lambda n: n["posted"], reverse=True),
                                     lambda n: [filters.url_key(n["url"])])[:40]
        news_failed += bad

    raw_jobs, jobs_failed = collect(sources.JOB_SOURCES)
    candidates = [j for j in raw_jobs if filters.is_candidate_job(j, now)]
    candidates = filters.dedupe(sorted(candidates, key=lambda j: j["posted"], reverse=True), filters.job_keys)
    unseen = [j for j in candidates if not is_seen(db, filters.job_keys(j))][:60]
    log.info("lowongan: %d mentah, %d lolos filter, %d belum pernah dikirim",
             len(raw_jobs), len(candidates), len(unseen))

    try:
        news_id, news_tech = rank_news(news["id"], news["tech"], cfg)
        jobs = rank_jobs(unseen, cfg) if unseen else []
        llm_note = ""
    except RuntimeError as err:
        log.error("LLM gagal, pakai urutan terbaru tanpa ranking: %s", err)
        news_id, news_tech, jobs = news["id"][:MAX_NEWS], news["tech"][:MAX_NEWS], unseen[:MAX_JOBS]
        llm_note = " | LLM down, tanpa ranking"

    jobs = [j for j in jobs if link_alive(j["url"])]
    failed = sorted(set(jobs_failed + [n.split()[0] for n in news_failed]))
    footer = (f"{len(raw_jobs)} lowongan dicek, {len(candidates)} lolos filter, "
              f"{len(candidates) - len(unseen)} sudah pernah dikirim"
              + (f" | sumber gagal: {', '.join(failed)}" if failed else "") + llm_note)
    local = now.astimezone(WIB)
    day = f"{HARI[local.weekday()]}, {local.day} {BULAN[local.month - 1]} {local.year}"
    news_text = filters.format_news(day, news_id, news_tech, now)
    jobs_text = filters.format_jobs(day, jobs, now, footer)

    if not dry_run:
        mark_seen(db, [k for j in jobs for k in filters.job_keys(j)]
                  + [filters.url_key(n["url"]) for n in news_id + news_tech])
    return news_text, jobs_text, jobs


WEEKLY_PROMPT = """Cari lowongan AI Engineer / ML Engineer / Data Scientist / Data Analyst level
entry-mid (fresh graduate sampai 3 tahun) di Jakarta atau remote, dari: Deloitte, PwC, EY, KPMG,
Rekrutmen Bersama BUMN (fhcibumn.id), Telkom, Telkomsel, Pertamina, BRI, Mandiri, BNI, BTN, PLN.
Gunakan query presisi (site:domain "kata kunci"); jangan merayapi portal satu per satu.

ATURAN KERAS:
- Hanya lowongan yang tanggal posting-nya terlihat dan <= 7 hari sebelum {today},
  ATAU batas akhir pendaftaran terlihat dan >= {today}. Tanpa tanggal = buang.
- Buang posisi senior/lead/manager/intern dan yang mensyaratkan > 3 tahun pengalaman.
- Link harus ke halaman detail lowongan resmi perusahaan, bukan agregator/blog loker.

Jawaban akhir HANYA JSON array (boleh kosong []):
[{{"title": "...", "company": "...", "location": "...", "url": "...",
  "posted": "YYYY-MM-DD atau null", "deadline": "YYYY-MM-DD atau null"}}]"""


def weekly(env: dict, db: sqlite3.Connection, now: datetime, dry_run: bool) -> str:
    today = now.astimezone(WIB).date()
    hermes_env = {**os.environ, "PATH": f"{HOME}/.hermes/bin:{HOME}/.local/bin:{os.environ.get('PATH', '')}"}
    found, model = None, ""
    for model in WEEKLY_MODELS:
        try:
            proc = subprocess.run(["hermes", "chat", "-m", model, "-q", WEEKLY_PROMPT.format(today=today)],
                                  capture_output=True, text=True, timeout=900, env=hermes_env)
        except subprocess.TimeoutExpired:
            log.warning("weekly %s timeout", model)
            continue
        raw = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", proc.stdout)
        (REPORT_DIR / f"weekly_raw_{today}.md").write_text(raw)
        found = filters.final_json_array(raw) if proc.returncode == 0 else None
        if found is not None:
            break
        log.warning("weekly %s tidak menghasilkan JSON (exit %s)", model, proc.returncode)
    if found is None:
        raise RuntimeError("semua model weekly gagal menghasilkan JSON")

    jobs = []
    for f in found if isinstance(found, list) else []:
        posted = sources.parse_date(f.get("posted") or "")
        deadline = sources.parse_date(f.get("deadline") or "")
        recent = posted is not None and now - posted <= timedelta(days=8)
        open_ = deadline is not None and deadline.date() >= today
        j = sources.job("Big4/BUMN", f.get("title", ""), f.get("company", ""), f.get("location", ""),
                        f.get("url", ""), posted or deadline)
        if (recent or open_) and j["url"].startswith("http") and not filters.TOO_SENIOR.search(j["title"]) \
                and not is_seen(db, filters.job_keys(j)) and link_alive(j["url"]):
            jobs.append({**j, "why": f"deadline {deadline.date()}" if deadline else ""})

    lines = [f"<b>Big 4 &amp; BUMN mingguan ({today})</b>"]
    lines += [f'{n}. <a href="{filters.esc(j["url"])}">{filters.esc(j["title"])}</a> | {filters.esc(j["company"])}'
              f' | {filters.esc(j["location"])}' + (f" | {filters.esc(j['why'])}" if j["why"] else "")
              for n, j in enumerate(jobs[:MAX_JOBS], 1)] or ["- tidak ada lowongan entry-mid yang masih buka"]
    lines.append(f"<i>{len(found)} hasil agent ({model}), {len(jobs)} lolos cek tanggal/level/link</i>")
    if not dry_run:
        mark_seen(db, [k for j in jobs[:MAX_JOBS] for k in filters.job_keys(j)])
    return None, "\n".join(lines), jobs[:MAX_JOBS]


def main() -> int:
    REPORT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(filename=REPORT_DIR / "execution.log", level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    weekly_mode, dry_run = "--weekly" in sys.argv, "--dry-run" in sys.argv
    if dry_run:
        logging.getLogger().addHandler(logging.StreamHandler())

    lock = open(REPORT_DIR / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.info("instance lain masih jalan, keluar")
        return 0

    env = load_env()
    now = datetime.now(timezone.utc)
    try:
        if not dry_run and not (env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID")):
            raise RuntimeError("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID belum diset")
        db = open_db()
        news_text, jobs_text, jobs = (weekly(env, db, now, dry_run) if weekly_mode
                                      else daily(env, model_config(env), db, now, dry_run))
        text = "\n\n".join(filter(None, [news_text, jobs_text]))
        name = "weekly" if weekly_mode else "digest"
        (REPORT_DIR / f"{name}_{now.astimezone(WIB).date()}.html").write_text(text)
        if dry_run:
            print(text)
            return 0
        ok = send(news_text, env) if news_text else True
        jenv = jobs_env(env)
        ok = send(jobs_text, jenv) and ok
        send_job_picker(db, jenv, jobs)
        if not ok:
            raise RuntimeError("sebagian pesan gagal terkirim")
        if not weekly_mode:
            tracker.init(db)
            tracker.kv_set(db, "digest_sent", now.astimezone(WIB).date().isoformat())
        log.info("%s terkirim (%d karakter)", name, len(text))
        return 0
    except Exception as err:
        log.exception("digest gagal")
        if not dry_run:
            notify_error(env, f"{type(err).__name__}: {err}. Cek ~/hermes_reports/execution.log")
        return 1


if __name__ == "__main__":
    sys.exit(main())
