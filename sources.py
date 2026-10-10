"""Fetch job and news items from feeds that expose a real posting date."""
from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129 Safari/537.36"
TIMEOUT = 25
RETRY_DELAY = 3

JOB_QUERIES = ["AI Engineer", "Machine Learning Engineer", "Data Scientist", "Data Analyst"]

NEWS_FEEDS = {
    "id": [
        ("Antara", "https://www.antaranews.com/rss/ekonomi.xml"),
        ("Antara", "https://www.antaranews.com/rss/politik.xml"),
        ("CNBC Indonesia", "https://www.cnbcindonesia.com/news/rss"),
    ],
    "tech": [
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ],
}


def get(url: str, tries: int = 2) -> bytes:
    """Retry once on network errors/timeouts; an HTTP error status is final."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            raise
        except OSError:  # URLError, socket.timeout
            if attempt == tries - 1:
                raise
            time.sleep(RETRY_DELAY)


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def strip_tags(text: str, limit: int = 300) -> str:
    clean = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()
    return clean[:limit]


def job(source, title, company, location, url, posted, snippet="", deadline=None) -> dict:
    return {
        "source": source,
        "title": strip_tags(title, 120),
        "company": strip_tags(company, 80),
        "location": strip_tags(location, 80),
        "url": url,
        "posted": posted,
        "deadline": deadline,
        "snippet": strip_tags(snippet),
    }


def kalibrr() -> list[dict]:
    out = []
    for q in JOB_QUERIES:
        qs = urllib.parse.urlencode({"limit": 40, "offset": 0, "text": q})
        data = json.loads(get(f"https://www.kalibrr.com/kjs/job_board/search?{qs}"))
        for j in data.get("jobs", []):
            loc = (j.get("google_location") or {}).get("address_components") or {}
            city = loc.get("city") or ""
            if j.get("is_work_from_home"):
                city = f"{city} (WFH)".strip()
            code = (j.get("company") or {}).get("code", "")
            out.append(job(
                "Kalibrr", j.get("name", ""), j.get("company_name", ""), city,
                f"https://www.kalibrr.com/c/{code}/jobs/{j.get('id')}/{j.get('slug', '')}",
                parse_date(j.get("activation_date", "")),
                j.get("qualifications", ""),
                parse_date(j.get("application_end_date") or ""),
            ))
    return out


def jobstreet() -> list[dict]:
    out = []
    for q in JOB_QUERIES:
        qs = urllib.parse.urlencode({
            "siteKey": "ID-Main", "sourcesystem": "houston", "keywords": q,
            "where": "Jakarta", "page": 1, "pageSize": 30, "daterange": 3, "locale": "id-ID",
        })
        data = json.loads(get(f"https://id.jobstreet.com/api/jobsearch/v5/search?{qs}"))
        for j in data.get("data", []):
            locs = ", ".join(x.get("label", "") for x in j.get("locations", []))
            out.append(job(
                "Jobstreet", j.get("title", ""), (j.get("advertiser") or {}).get("description", ""),
                locs, f"https://id.jobstreet.com/id/job/{j.get('id')}",
                parse_date(j.get("listingDate", "")), j.get("teaser", ""),
            ))
    return out


LI_CARD = re.compile(r'<li>(.*?)</li>', re.S)


def _li_field(block: str, cls: str) -> str:
    m = re.search(rf'class="{cls}[^"]*"[^>]*>(.*?)</', block, re.S)
    return strip_tags(m.group(1)) if m else ""


def linkedin() -> list[dict]:
    out = []
    searches = [{"location": "Jakarta"}, {"location": "Indonesia", "f_WT": "2"}]
    for q in JOB_QUERIES:
        for extra in searches:
            qs = urllib.parse.urlencode({
                "keywords": q, "f_TPR": "r259200", "f_E": "1,2,3", "start": 0, **extra,
            })
            page = get(f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{qs}").decode("utf-8", "replace")
            for block in LI_CARD.findall(page):
                jid = re.search(r"jobPosting:(\d+)", block)
                when = re.search(r'datetime="([^"]+)"', block)
                if not jid:
                    continue
                company = re.search(r'base-search-card__subtitle[^>]*>\s*(?:<a[^>]*>)?(.*?)</', block, re.S)
                out.append(job(
                    "LinkedIn", _li_field(block, "base-search-card__title"),
                    strip_tags(company.group(1)) if company else "",
                    _li_field(block, "job-search-card__location") + (" (Remote)" if extra.get("f_WT") else ""),
                    f"https://www.linkedin.com/jobs/view/{jid.group(1)}",
                    parse_date(when.group(1)) if when else None,
                ))
    return out


REMOTE_OK_REGION = re.compile(r"worldwide|anywhere|global|asia|apac|indonesia|southeast|^remote$|^$", re.I)


def remoteok() -> list[dict]:
    data = json.loads(get("https://remoteok.com/api"))[1:]
    return [
        job("RemoteOK", j.get("position", ""), j.get("company", ""), j.get("location") or "Remote",
            j.get("url", ""), parse_date(j.get("date", "")), j.get("description", ""))
        for j in data
        if REMOTE_OK_REGION.search((j.get("location") or "").strip())
    ]


def weworkremotely() -> list[dict]:
    root = ET.fromstring(get("https://weworkremotely.com/remote-jobs.rss"))
    out = []
    for item in root.iter("item"):
        region = item.findtext("region") or ""
        if not REMOTE_OK_REGION.search(region.strip()):
            continue
        company, _, title = (item.findtext("title") or "").partition(":")
        out.append(job("WeWorkRemotely", title or company, company if title else "", region or "Remote",
                       item.findtext("link") or "", parse_date(item.findtext("pubDate") or ""),
                       item.findtext("description") or ""))
    return out


JOB_SOURCES = {
    "Kalibrr": kalibrr,
    "Jobstreet": jobstreet,
    "LinkedIn": linkedin,
    "RemoteOK": remoteok,
    "WeWorkRemotely": weworkremotely,
}

ATOM = "{http://www.w3.org/2005/Atom}"


def rss(source: str, url: str) -> list[dict]:
    root = ET.fromstring(get(url))
    items = []
    for it in root.iter("item"):
        items.append({
            "source": source, "title": strip_tags(it.findtext("title") or "", 160),
            "url": (it.findtext("link") or "").strip(),
            "posted": parse_date(it.findtext("pubDate") or ""),
            "snippet": strip_tags(it.findtext("description") or "", 250),
        })
    for it in root.iter(f"{ATOM}entry"):
        link = it.find(f"{ATOM}link")
        items.append({
            "source": source, "title": strip_tags(it.findtext(f"{ATOM}title") or "", 160),
            "url": link.get("href", "") if link is not None else "",
            "posted": parse_date(it.findtext(f"{ATOM}published") or it.findtext(f"{ATOM}updated") or ""),
            "snippet": strip_tags(it.findtext(f"{ATOM}summary") or it.findtext(f"{ATOM}content") or "", 250),
        })
    return items
