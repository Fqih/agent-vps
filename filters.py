"""Pure filtering and formatting helpers (no network, no disk)."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from datetime import datetime, timedelta

ROLE = re.compile(
    r"\b(ai|a\.i\.|ml|mlops|llm|nlp|genai|machine learning|deep learning|computer vision|"
    r"artificial intelligence|data scien\w*|data analy\w*|prompt engineer\w*)\b",
    re.I,
)
TOO_SENIOR = re.compile(
    r"\b(senior|sr\.?|lead|principal|head|manager|director|vp|vice president|staff|"
    r"architect|chief|expert|specialist iii|intern|internship|magang|trainee programme)\b",
    re.I,
)
MANY_YEARS = re.compile(r"\b([4-9]|1\d)\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|tahun|yrs)\b", re.I)
LOCATION_OK = re.compile(r"jakarta|remote|wfh|anywhere|worldwide|global|asia|apac|indonesia", re.I)


def is_candidate_job(job: dict, now: datetime, max_age_days: int = 3) -> bool:
    posted = job.get("posted")
    if posted is None or now - posted > timedelta(days=max_age_days):
        return False
    deadline = job.get("deadline")
    if deadline is not None and deadline < now:
        return False
    title = job.get("title", "")
    if not ROLE.search(title) or TOO_SENIOR.search(title):
        return False
    if MANY_YEARS.search(job.get("snippet", "")):
        return False
    return bool(LOCATION_OK.search(job.get("location", "")))


def is_fresh_news(item: dict, now: datetime, max_age_hours: int = 30) -> bool:
    posted = item.get("posted")
    return bool(item.get("url")) and posted is not None and now - posted <= timedelta(hours=max_age_hours)


def url_key(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    return re.sub(r"^www\.", "", p.netloc.lower()) + p.path.rstrip("/")


def job_keys(job: dict) -> list[str]:
    """A job counts as seen if its URL or its normalized title+company was sent before."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    keys = [url_key(job["url"])]
    if job.get("company"):
        keys.append(f"tc:{norm(job['title'])}|{norm(job['company'])}")
    return keys


def dedupe(items: list[dict], key_fn) -> list[dict]:
    seen, out = set(), []
    for it in items:
        keys = key_fn(it)
        if any(k in seen for k in keys):
            continue
        seen.update(keys)
        out.append(it)
    return out


def age_label(posted: datetime | None, now: datetime) -> str:
    if posted is None:
        return "tanggal ?"
    hours = int((now - posted).total_seconds() // 3600)
    if hours < 24:
        return f"{max(hours, 1)} jam lalu"
    return f"{hours // 24} hari lalu"


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def format_news(day: str, news_id: list[dict], news_tech: list[dict], now: datetime) -> str:
    lines = [f"<b>Berita {esc(day)}</b>", ""]
    for title, items in (("Indonesia", news_id), ("AI &amp; Tech", news_tech)):
        lines.append(f"<b>{title}</b>")
        if not items:
            lines.append("- tidak ada berita baru")
        for n in items:
            lines.append(f'- <a href="{esc(n["url"])}">{esc(n["title"])}</a> ({esc(n["source"])}, '
                         f'{age_label(n["posted"], now)})')
            if n.get("summary"):
                lines.append(f"  {esc(n['summary'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_jobs(day: str, jobs: list[dict], now: datetime, footer: str) -> str:
    lines = [f"<b>Lowongan entry-mid {esc(day)}</b>"]
    if not jobs:
        lines.append("- tidak ada lowongan baru yang cocok")
    for n, j in enumerate(jobs, 1):
        lines.append(f'{n}. <a href="{esc(j["url"])}">{esc(j["title"])}</a> | {esc(j["company"])} | '
                     f'{esc(j["location"])} | {age_label(j["posted"], now)}')
        if j.get("why"):
            lines.append(f"  {esc(j['why'])}")
    lines += ["", f"<i>{esc(footer)}</i>"]
    return "\n".join(lines)


def final_json_array(transcript: str):
    """Parse the JSON array inside hermes' last answer box; the echoed prompt also contains '[]'."""
    box = transcript.rsplit("☤ Hermes", 1)
    if len(box) < 2:
        return None
    body = box[1].split("╰", 1)[0]
    body = "\n".join(line.strip("│ ") for line in body.splitlines()[1:])
    start, end = body.find("["), body.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        parsed = json.loads(body[start:end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, list) else None
