"""Uptime, VPS health and SSH-login checks. Alerts only on state changes."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FAILS_BEFORE_ALERT = 2
AUTH_LOG = Path("/var/log/auth.log")
DEFAULT_SITES = {
    "portfolio": "https://faqihhakim.tech",
    "skripsi-demo": "https://skripsi.faqihhakim.tech",
    "9router": "http://127.0.0.1:20128",
    "headroom": "http://127.0.0.1:8787",
}
CONTAINERS = ("9router", "headroom")
SSH_ACCEPTED = re.compile(r"Accepted (\w+) for (\S+) from (\S+)")


def init(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sites (name TEXT PRIMARY KEY, url TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS checks (name TEXT PRIMARY KEY, ok INTEGER NOT NULL,
                                           fails INTEGER NOT NULL, since TEXT NOT NULL, detail TEXT);
    """)
    if not db.execute("SELECT 1 FROM sites LIMIT 1").fetchone():
        db.executemany("INSERT INTO sites VALUES (?, ?)", DEFAULT_SITES.items())
    db.commit()


def check_url(url: str) -> tuple[bool, str]:
    """Any HTTP answer below 500 means the service is up (401/403/404 still prove it's alive)."""
    req = urllib.request.Request(url, headers={"User-Agent": "infobot-uptime/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as err:
        return err.code < 500, f"HTTP {err.code}"
    except (urllib.error.URLError, OSError) as err:
        return False, str(getattr(err, "reason", err))[:80]


def system_checks() -> dict[str, tuple[bool, str]]:
    out = {}
    disk = shutil.disk_usage("/")
    pct = disk.used * 100 // disk.total
    out["disk"] = (pct < 85, f"{pct}% terpakai")
    mem = dict(re.findall(r"(\w+):\s+(\d+) kB", Path("/proc/meminfo").read_text()))
    avail_mb = int(mem.get("MemAvailable", 0)) // 1024
    out["ram"] = (avail_mb >= 150, f"{avail_mb} MB tersedia")
    try:
        running = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True,
                                 text=True, timeout=20).stdout.split()
        for c in CONTAINERS:
            out[f"container:{c}"] = (c in running, "jalan" if c in running else "tidak jalan")
    except (OSError, subprocess.SubprocessError) as err:
        out["docker"] = (False, str(err)[:80])
    failed = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain"], capture_output=True,
                            text=True, timeout=20).stdout.split("\n")
    units = [line.split()[0] for line in failed if line.strip()]
    out["systemd"] = (not units, ", ".join(units) or "semua unit normal")
    return out


def run_checks(db: sqlite3.Connection) -> dict[str, tuple[bool, str]]:
    results = {f"site:{name}": check_url(url) for name, url in db.execute("SELECT name, url FROM sites")}
    results.update(system_checks())
    return results


def transitions(db: sqlite3.Connection, results: dict, now: datetime) -> list[str]:
    """Update stored state; return alert lines for checks that just went down or recovered."""
    alerts = []
    for name, (ok, detail) in results.items():
        row = db.execute("SELECT ok, fails, since FROM checks WHERE name = ?", (name,)).fetchone()
        prev_ok, fails, since = row if row else (1, 0, now.isoformat())
        fails = 0 if ok else fails + 1
        if not ok and prev_ok and fails >= FAILS_BEFORE_ALERT:
            alerts.append(f"DOWN {name}: {detail}")
            prev_ok, since = 0, now.isoformat()
        elif ok and not prev_ok:
            mins = int((now - datetime.fromisoformat(since)).total_seconds() // 60)
            alerts.append(f"PULIH {name} setelah {mins} menit ({detail})")
            prev_ok, since = 1, now.isoformat()
        db.execute("INSERT OR REPLACE INTO checks VALUES (?, ?, ?, ?, ?)", (name, prev_ok, fails, since, detail))
    db.commit()
    return alerts


def status_text(db: sqlite3.Connection) -> str:
    rows = db.execute("SELECT name, ok, detail FROM checks ORDER BY name").fetchall()
    if not rows:
        return "Belum ada hasil cek, tunggu beberapa menit."
    return "<b>Status</b>\n" + "\n".join(f"{'OK ' if ok else 'DOWN'} {n}: {d}" for n, ok, d in rows)


def new_ssh_logins(offset: int, log_path: Path = AUTH_LOG) -> tuple[list[str], int]:
    """Return (alerts, new_offset). Starts from the end on first run; handles log rotation."""
    try:
        size = log_path.stat().st_size
    except OSError:
        return [], offset
    if offset < 0 or offset > size:
        return [], size if offset < 0 else 0
    with open(log_path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read().decode("utf-8", "replace")
    alerts = [f"Login SSH: user {m.group(2)} dari {m.group(3)} ({m.group(1)})"
              for m in SSH_ACCEPTED.finditer(chunk)]
    return alerts, size


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


DOMAINS = ("faqihhakim.tech",)
EXPIRY_WARN_DAYS = 30


def domain_days_left(domain: str, now: datetime) -> int | None:
    """Days until registration expiry, from public RDAP."""
    try:
        with urllib.request.urlopen(f"https://rdap.org/domain/{domain}", timeout=20) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return expiry_days(data, now)


def expiry_days(rdap: dict, now: datetime) -> int | None:
    for ev in rdap.get("events", []):
        if ev.get("eventAction") == "expiration":
            when = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            return (when - now).days
    return None
