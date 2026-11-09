"""Keep idle Gemini quota busy: when the worker has nothing to do and Gemini
still has quota above the reserve, queue useful work, most valuable first.

Sources in priority order: new job postings (match score, brief, cover
letter), new commits in the owner's public GitHub repos (review), unread
read-later links (deep summary), then interview questions for the /soal bank.
Every task runs on the `gemini` chain (Antigravity only), so the filler never
spends Codex or Claude quota.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone

import practice
from hub import tasks
from hub.collectors.common import ro

CHAIN = "gemini"
RESERVE = 20            # percent of Gemini quota kept for interactive use
MAX_QUEUED = 3          # filler never queues more than this ahead of the worker
FILL_EVERY = 120        # seconds between fill attempts while the worker is idle
JOB_DAYS = 14
QUESTION_BANK_MAX = 300  # unasked questions waiting in the /soal bank
QUOTA_MAX_AGE = timedelta(minutes=30)  # hub-status refreshes every 15 minutes
GITHUB_EVERY = 3600
GITHUB_DAYS = 7
GITHUB_REPOS = 5
GITHUB_BUDGET = 20      # seconds the idle worker may spend listing commits
STATUS_URL = "http://127.0.0.1:8090/status"
SCORE = re.compile(r"^Skor: (\d+)/100")
log = logging.getLogger("hub.filler")
_github_cache: dict = {}


def has_room(quota, now: datetime) -> bool:
    """True when a fresh reading puts every known Gemini window above the reserve.
    Unknown or stale quota means no: better idle than spend the interactive reserve."""
    if not isinstance(quota, dict):
        return False
    try:
        fresh = now - datetime.fromisoformat(quota["at"]) <= QUOTA_MAX_AGE
    except (KeyError, TypeError, ValueError):
        return False
    known = [quota.get(k) for k in ("session", "weekly") if isinstance(quota.get(k), (int, float))]
    return fresh and bool(known) and all(v > RESERVE for v in known)


def gemini_quota(env: dict):
    """Gemini quota as hub-status last saw it (refreshed there every 15 minutes)."""
    query = urllib.parse.urlencode({"token": env.get("STATUS_TOKEN", ""), "only": "quota"})
    url = env.get("STATUS_LOCAL_URL", STATUS_URL) + "?" + query
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp).get("quota", {}).get("gemini")


def _known(db, dedup_key: str) -> bool:
    return db.execute("SELECT 1 FROM tasks WHERE dedup_key = ?", (dedup_key,)).fetchone() is not None


def job_candidates(state, now: datetime) -> list:
    since = (now - timedelta(days=JOB_DAYS)).isoformat()
    rows = state.execute(
        "SELECT id, title, company, location, url FROM jobs WHERE status = 'baru' AND created_at >= ? "
        "AND (feedback IS NULL OR feedback >= 0) ORDER BY created_at DESC", (since,)).fetchall()
    return [("fill.job", {"job_id": i, "title": f"Nilai: {t or '?'} @ {c or '?'}", "job_title": t,
                          "company": c, "location": loc, "url": u}, f"fill:job:{i}")
            for i, t, c, loc, u in rows]


def read_candidates(state) -> list:
    rows = state.execute("SELECT id, url, title FROM reads WHERE done = 0 ORDER BY id").fetchall()
    return [("fill.read", {"read_id": i, "url": u, "title": f"Ringkas: {t or u}"[:120]}, f"fill:read:{i}")
            for i, u, t in rows]


def _github_api(path: str, env: dict):
    headers = {"User-Agent": "hub-filler", "Accept": "application/vnd.github+json"}
    if env.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {env['GITHUB_TOKEN']}"
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def github_candidates(env: dict, now: datetime, api=_github_api) -> list:
    """Commits from the last week in recently pushed repos, re-listed at most hourly
    (the unauthenticated API allows 60 calls an hour)."""
    hit = _github_cache.get("value")
    if hit is not None and time.monotonic() - _github_cache["at"] < GITHUB_EVERY:
        return hit
    user = env.get("GITHUB_USER", "Fqih")
    since = now - timedelta(days=GITHUB_DAYS)
    since_q = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, started = [], time.monotonic()
    try:
        repos = api(f"/users/{user}/repos?sort=pushed&per_page=10", env)
    except Exception as err:  # GitHub down or rate limited: try again next hour
        log.warning("github: %s", err)
        repos = []
    recent = [r for r in repos if not r.get("fork") and r.get("pushed_at")
              and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) >= since][:GITHUB_REPOS]
    for repo in recent:
        if time.monotonic() - started > GITHUB_BUDGET:  # the worker must get back to real tasks
            break
        try:
            commits = api(f"/repos/{repo['full_name']}/commits?since={since_q}&per_page=10", env)
        except Exception as err:  # one empty or broken repo must not hide the others
            log.warning("github %s: %s", repo["full_name"], err)
            continue
        for commit in commits:
            if len(commit.get("parents", [])) > 1:  # merges repeat work already reviewed
                continue
            subject = (commit["commit"]["message"].splitlines() or [""])[0][:80]
            out.append(("fill.review", {"repo": repo["full_name"], "sha": commit["sha"],
                                        "title": f"Review {repo['full_name']}: {subject}"},
                        f"fill:gh:{commit['sha']}"))
    _github_cache.update(value=out, at=time.monotonic())
    return out


def question_candidates(state, queued: int, needed: int) -> list:
    bank = state.execute("SELECT COUNT(*) FROM questions WHERE source = 'bank' AND due IS NULL").fetchone()[0]
    room = max(0, QUESTION_BANK_MAX - bank - queued)
    total = state.execute("SELECT COUNT(*) FROM questions").fetchone()[0] + queued
    topics = practice.TOPICS
    return [("fill.question", {"topic": topics[(total + i) % len(topics)],
                               "title": f"Soal {topics[(total + i) % len(topics)]}"}, None)
            for i in range(min(room, needed))]


def fill(db, ctx: dict, now: datetime | None = None, quota="fetch") -> int:
    """Queue up to MAX_QUEUED tasks when Gemini has room; returns how many were added."""
    now = now or tasks.utcnow()
    if quota == "fetch":
        try:
            quota = gemini_quota(ctx["env"])
        except Exception as err:  # hub-status down: just stay idle, no traceback every 2 minutes
            log.warning("filler: kuota tidak terbaca: %s", err)
            return 0
    if not has_room(quota, now):
        return 0
    needed = MAX_QUEUED - tasks.counts(db, now)["queued"]
    if needed <= 0:
        return 0
    queued_questions = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE kind = 'fill.question' AND status IN ('queued', 'running')").fetchone()[0]
    with closing(ro(ctx["state_db"])) as state:
        fresh = [c for c in job_candidates(state, now) + github_candidates(ctx["env"], now) + read_candidates(state)
                 if not _known(db, c[2])][:needed]
        fresh += question_candidates(state, queued_questions, needed - len(fresh))
    for kind, payload, dedup in fresh:
        tasks.enqueue(db, kind, dict(payload, notify=False), chain=CHAIN, dedup_key=dedup, now=now)
    if fresh:
        log.info("filler: %d tugas ditambahkan (%s)", len(fresh), ", ".join(k for k, _, _ in fresh))
    return len(fresh)


def summary(db, since: datetime) -> str | None:
    """One line for the morning push: what the filler finished since `since`."""
    rows = db.execute("SELECT kind, payload, result FROM tasks WHERE status = 'done' AND kind LIKE 'fill.%' "
                      "AND finished_at >= ?", (tasks.iso(since),)).fetchall()
    if not rows:
        return None
    names = {"fill.job": "lowongan", "fill.review": "review", "fill.read": "bacaan", "fill.question": "soal"}
    counts: dict = {}
    best = None
    for kind, payload, result in rows:
        counts[kind] = counts.get(kind, 0) + 1
        m = SCORE.match(result or "") if kind == "fill.job" else None
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), json.loads(payload).get("title", "")[len("Nilai: "):])
    parts = ", ".join(f"{n} {names.get(k, k)}" for k, n in counts.items())
    line = f"Gemini kemarin: {len(rows)} tugas ({parts})"
    return line + (f". Lowongan terbaik: {best[1]} ({best[0]})" if best else "")
