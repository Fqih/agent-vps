"""VPS health: load, RAM, disk, failing monitor checks, last backup."""
from __future__ import annotations

import os
import re
import shutil
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from hub.collectors.common import WIB, ro


def _ram_percent(meminfo: Path) -> int:
    mem = dict(re.findall(r"(\w+):\s+(\d+) kB", meminfo.read_text()))
    return round(100 - int(mem["MemAvailable"]) * 100 / int(mem["MemTotal"]))


def _backup_ok(dest: Path, now: datetime) -> bool:
    """A snapshot from today or yesterday (WIB) exists; the 03:00 run makes today's."""
    day = now.astimezone(WIB).date()
    return any(any((dest / d.isoformat()).glob("*.sqlite.gz")) for d in (day, day - timedelta(days=1)))


def collect(ctx: dict, now: datetime) -> dict:
    load1 = float(Path(ctx.get("loadavg", "/proc/loadavg")).read_text().split()[0])
    disk = shutil.disk_usage("/")
    with closing(ro(ctx["state_db"])) as db:
        down = [name for (name,) in db.execute("SELECT name FROM checks WHERE ok = 0 ORDER BY name")]
    return {
        "cpu": min(100, round(load1 / (os.cpu_count() or 1) * 100)),
        "ram": _ram_percent(Path(ctx.get("meminfo", "/proc/meminfo"))),
        "disk": disk.used * 100 // disk.total,
        "down": down,
        "backup_ok": _backup_ok(Path(ctx["backups"]), now),
    }
