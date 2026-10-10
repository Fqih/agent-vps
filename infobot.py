#!/usr/bin/env python3
"""Personal Telegram bots, one process:

- jobs bot (JOBS_BOT_TOKEN): job tracker, company briefs, interview practice
- info bot (TELEGRAM_BOT_TOKEN): read-later links, VPS/website status, alerts

Both answer ONLY the owner (TELEGRAM_CHAT_ID); everything else is silently ignored.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from html import escape

import brief
import monitor
import practice
import readlater
import tg
import tracker
from digest import DB_PATH, REPORT_DIR, WIB, jobs_env, load_env, model_config

CHECK_EVERY = timedelta(minutes=5)
DIGEST_DEADLINE = (7, 45)                   # WIB; the 07:00 digest normally lands by 07:02
DAYTIME = range(8, 21)                     # WIB, no pings at night
PRACTICE_HOUR = 9                          # daily interview question, WIB
JOB_RECAP = (6, 19)                        # Sunday 19:00 WIB
READ_RECAP = (5, 9)                        # Saturday 09:00 WIB

JOBS_HELP = """<b>Bot lamaran</b>
/lamaran - lamaran aktif
/j&lt;id&gt; - detail + ubah status
/tambah &lt;url&gt; &lt;judul | perusahaan&gt; - catat lowongan manual
/brief &lt;id&gt; - brief perusahaan &amp; persiapan interview
/rekap - rekap lamaran
/soal - latihan interview sekarang
/skip - lewati soal aktif"""
INFO_HELP = """<b>Bot info</b>
Kirim link apa saja untuk disimpan + diringkas.
/bacaan - daftar belum dibaca
/status - status website &amp; VPS
/pantau &lt;nama&gt; &lt;url&gt; - pantau website
/lepas &lt;nama&gt; - berhenti memantau"""

log = logging.getLogger("infobot")


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH, timeout=30)
    for mod in (tracker, monitor, readlater, practice):
        mod.init(db)
    return db


def background(fn, *args) -> None:
    """LLM calls take 10-60 s; run them off the polling loop."""
    def run():
        try:
            fn(*args)
        except Exception:
            log.exception("background %s gagal", fn.__name__)
    threading.Thread(target=run, daemon=True).start()


def is_owner(update: dict, owner: int) -> bool:
    for key in ("message", "callback_query"):
        part = update.get(key)
        if part:
            chat = (part.get("message") or part).get("chat", {})
            return part.get("from", {}).get("id") == owner and chat.get("id") == owner
    return False


def split_command(text: str) -> tuple[str, str]:
    cmd, _, arg = text.strip().partition(" ")
    return cmd.split("@")[0].lower(), arg.strip()


# ---------- background jobs ----------

def send_brief(env: dict, job: dict, stage: str) -> None:
    tg.send(env, brief.generate(job, stage, model_config(env)))


def send_question(env: dict) -> None:
    db = connect()
    qid, text = practice.ask(db, model_config(env), monitor.now_utc())
    tracker.kv_set(db, "pending_q", str(qid))
    tg.send(env, text)


def grade_answer(env: dict, qid: int, answer: str) -> None:
    db = connect()
    tg.send(env, practice.grade(db, qid, answer, model_config(env), monitor.now_utc()))


def save_link(env: dict, url: str) -> None:
    db = connect()
    title, summary = readlater.summarize(url, model_config(env))
    rid = readlater.save(db, url, title, summary)
    tg.send(env, *readlater.card(rid, url, title, summary))


# ---------- jobs bot ----------

def jobs_message(db: sqlite3.Connection, env: dict, text: str) -> None:
    if not text.startswith("/"):
        qid = tracker.kv_get(db, "pending_q")
        if qid:
            tracker.kv_set(db, "pending_q", "")
            tg.send(env, "Menilai jawaban...")
            background(grade_answer, env, int(qid), text)
        else:
            tg.send(env, "Tidak ada soal aktif. /soal untuk mulai latihan.")
        return
    cmd, arg = split_command(text)
    m = re.fullmatch(r"/j(\d+)", cmd)
    if m:
        job = tracker.get(db, int(m.group(1)))
        if job:
            tg.send(env, *tracker.card(job))
        else:
            tg.send(env, "Lowongan tidak ditemukan.")
    elif cmd == "/lamaran":
        tg.send(env, tracker.active_list(db))
    elif cmd == "/tambah":
        url, _, rest = arg.partition(" ")
        if not url.startswith("http"):
            tg.send(env, "Format: /tambah &lt;url&gt; &lt;judul | perusahaan&gt;")
            return
        title, _, company = rest.partition("|")
        jid = tracker.record(db, {"url": url, "title": title.strip() or url, "company": company.strip(),
                                  "source": "manual"}, status="disimpan")
        tg.send(env, *tracker.card(tracker.get(db, jid)))
    elif cmd == "/brief":
        job = tracker.get(db, int(arg)) if arg.isdigit() else None
        if not job:
            tg.send(env, "Format: /brief &lt;id&gt; (lihat id di /lamaran)")
            return
        tg.send(env, "Menyusun brief...")
        background(send_brief, env, job, "interview" if job["status"] == "interview" else "dilamar")
    elif cmd == "/rekap":
        tg.send(env, tracker.recap(db, monitor.now_utc()))
    elif cmd == "/soal":
        background(send_question, env)
    elif cmd == "/skip":
        tracker.kv_set(db, "pending_q", "")
        tg.send(env, "Soal dilewati.")
    else:
        tg.send(env, JOBS_HELP)


def jobs_callback(db: sqlite3.Connection, env: dict, cq: dict) -> None:
    nf = re.fullmatch(r"nf:(\d+)", cq.get("data", ""))
    if nf:
        ok = tracker.set_feedback(db, int(nf.group(1)), -1)
        tg.call(env, "answerCallbackQuery", callback_query_id=cq["id"],
                text="Dicatat: tidak cocok" if ok else "Tidak valid")
        return
    m = re.fullmatch(r"(st|sv):(\d+):?(\w*)", cq.get("data", ""))
    action = (m.group(3) or "disimpan") if m else ""
    job = tracker.set_status(db, int(m.group(2)), action) if m else None
    tg.call(env, "answerCallbackQuery", callback_query_id=cq["id"], text="Tersimpan" if job else "Tidak valid")
    if not job:
        return
    text, buttons = tracker.card(job)
    msg = cq.get("message", {})
    if m.group(1) == "sv":   # tapped on the daily picker: keep it, post the card below
        tg.send(env, text, buttons)
    else:
        tg.call(env, "editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                text=text, parse_mode="HTML", disable_web_page_preview=True,
                reply_markup={"inline_keyboard": buttons})
    if action in ("dilamar", "interview"):
        background(send_brief, env, job, action)


# ---------- info bot ----------

def info_message(db: sqlite3.Connection, env: dict, text: str) -> None:
    if not text.startswith("/"):
        url = readlater.first_url(text)
        if url:
            tg.send(env, "Menyimpan &amp; meringkas...")
            background(save_link, env, url)
        else:
            tg.send(env, INFO_HELP)
        return
    cmd, arg = split_command(text)
    if cmd == "/bacaan":
        tg.send(env, readlater.unread(db))
    elif cmd == "/status":
        tg.send(env, monitor.status_text(db))
    elif cmd == "/pantau":
        name, _, url = arg.partition(" ")
        if not (name and url.strip().startswith("http")):
            tg.send(env, "Format: /pantau &lt;nama&gt; &lt;url&gt;")
            return
        db.execute("INSERT OR REPLACE INTO sites VALUES (?, ?)", (name, url.strip()))
        db.commit()
        tg.send(env, f"Memantau {escape(name)}: {escape(url.strip())}")
    elif cmd == "/lepas":
        db.execute("DELETE FROM sites WHERE name = ?", (arg,))
        db.execute("DELETE FROM checks WHERE name = ?", (f"site:{arg}",))
        db.commit()
        tg.send(env, f"Berhenti memantau {escape(arg)}")
    else:
        tg.send(env, INFO_HELP)


def info_callback(db: sqlite3.Connection, env: dict, cq: dict) -> None:
    m = re.fullmatch(r"rd:(\d+)", cq.get("data", ""))
    ok = readlater.mark_done(db, int(m.group(1))) if m else False
    tg.call(env, "answerCallbackQuery", callback_query_id=cq["id"], text="Ditandai dibaca" if ok else "Tidak valid")
    if ok:
        msg = cq["message"]
        tg.call(env, "editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                reply_markup={"inline_keyboard": []})


# ---------- loops ----------

def poll(name: str, env: dict, owner: int, on_message, on_callback, commands: list) -> None:
    db = connect()
    tg.call(env, "setMyCommands", commands=[{"command": c, "description": d} for c, d in commands])
    offset_key = "update_offset" if name == "jobs" else f"update_offset:{name}"
    offset = int(tracker.kv_get(db, offset_key, "0"))
    while True:
        try:
            resp = tg.call(env, "getUpdates", http_timeout=40, timeout=25, offset=offset,
                           allowed_updates=["message", "callback_query"])
            if not resp.get("ok"):
                log.warning("%s getUpdates: %s", name, resp.get("description"))
                time.sleep(10)
            for upd in resp.get("result", []):
                offset = upd["update_id"] + 1
                tracker.kv_set(db, offset_key, str(offset))
                if not is_owner(upd, owner):
                    log.warning("%s: abaikan update dari non-owner", name)
                elif "callback_query" in upd:
                    on_callback(db, env, upd["callback_query"])
                elif upd.get("message", {}).get("text"):
                    on_message(db, env, upd["message"]["text"])
        except Exception:
            log.exception("%s loop error", name)
            time.sleep(10)


def once(db: sqlite3.Connection, key: str, value: str) -> bool:
    """True the first time `value` is seen for `key` (daily/weekly schedules survive restarts)."""
    if tracker.kv_get(db, key) == value:
        return False
    tracker.kv_set(db, key, value)
    return True


def digest_missing(db: sqlite3.Connection, local: datetime) -> bool:
    return ((local.hour, local.minute) >= DIGEST_DEADLINE
            and tracker.kv_get(db, "digest_sent") != local.date().isoformat())


def scheduled(db: sqlite3.Connection, jobs: dict, info: dict, state: dict) -> None:
    now = monitor.now_utc()
    local = now.astimezone(WIB)
    today, week = local.date().isoformat(), local.strftime("%G-W%V")

    alerts, offset = monitor.new_ssh_logins(int(tracker.kv_get(db, "auth_offset", "-1")))
    tracker.kv_set(db, "auth_offset", str(offset))
    for a in alerts:
        tg.send(info, escape(a))

    if now - state.get("last_check", datetime.min.replace(tzinfo=timezone.utc)) >= CHECK_EVERY:
        state["last_check"] = now
        alerts = monitor.transitions(db, monitor.run_checks(db), now)
        if alerts:
            tg.send(info, "<b>Monitor</b>\n" + escape("\n".join(alerts)))

    if digest_missing(db, local) and once(db, "digest_alert", today):
        tg.send(info, "<b>Digest hari ini belum terkirim.</b> Cek ~/hermes_reports/execution.log")

    if local.hour not in DAYTIME:
        return
    for job in tracker.due_reminders(db, now):
        text, buttons = tracker.card(job)
        tg.send(jobs, "Waktunya follow-up (7 hari sejak update terakhir):\n" + text, buttons)
    if once(db, "domain_check", today):
        for domain in monitor.DOMAINS:
            days = monitor.domain_days_left(domain, now)
            if days is not None and days <= monitor.EXPIRY_WARN_DAYS:
                tg.send(info, f"<b>Domain {escape(domain)} habis dalam {days} hari.</b> Perpanjang sekarang.")
    if local.hour >= PRACTICE_HOUR and once(db, "practice_day", today):
        background(send_question, jobs)
    if local.weekday() == JOB_RECAP[0] and local.hour >= JOB_RECAP[1] and once(db, "recap_week", week):
        tg.send(jobs, tracker.recap(db, now))
    if local.weekday() == READ_RECAP[0] and local.hour >= READ_RECAP[1] and once(db, "read_recap_week", week):
        text = readlater.weekly_recap(db, now)
        if text:
            tg.send(info, text)


def main() -> None:
    logging.basicConfig(filename=REPORT_DIR / "infobot.log", level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s %(threadName)s %(message)s")
    info = load_env()
    jobs = jobs_env(info)
    owner = int(info["TELEGRAM_CHAT_ID"])
    threading.Thread(target=poll, name="jobs", daemon=True, args=(
        "jobs", jobs, owner, jobs_message, jobs_callback,
        [("lamaran", "Lamaran aktif"), ("tambah", "Catat lowongan manual"), ("brief", "Brief perusahaan"),
         ("rekap", "Rekap lamaran"), ("soal", "Latihan interview"), ("skip", "Lewati soal")])).start()
    if info["TELEGRAM_BOT_TOKEN"] != jobs["TELEGRAM_BOT_TOKEN"]:
        threading.Thread(target=poll, name="info", daemon=True, args=(
            "info", info, owner, info_message, info_callback,
            [("bacaan", "Belum dibaca"), ("status", "Status website & VPS"),
             ("pantau", "Pantau website"), ("lepas", "Hapus pantauan")])).start()
    db, state = connect(), {}
    log.info("infobot jalan")
    while True:
        try:
            scheduled(db, jobs, info, state)
        except Exception:
            log.exception("scheduler error")
        time.sleep(30)


if __name__ == "__main__":
    main()
