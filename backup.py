#!/usr/bin/env python3
"""Daily consistent snapshot of the live SQLite DBs, gzip'd, keeping the last 7 days."""
import gzip
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

HOME = Path.home()
DBS = {"9router": HOME / "9router" / "data" / "db" / "data.sqlite", "hermes-state": HOME / ".hermes" / "state.db"}
DEST = HOME / "backups"
KEEP = 7


def snapshot(name: str, src: Path, day_dir: Path) -> Path:
    tmp = day_dir / f"{name}.sqlite"
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(tmp) as d:
        s.backup(d)
    out = tmp.with_suffix(".sqlite.gz")
    with open(tmp, "rb") as fi, gzip.open(out, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    tmp.unlink()
    return out


def main() -> int:
    day_dir = DEST / date.today().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    DEST.chmod(0o700)
    failed = 0
    for name, src in DBS.items():
        try:
            print(f"{name}: {snapshot(name, src, day_dir)}")
        except (sqlite3.Error, OSError) as err:
            print(f"{name}: GAGAL {err}", file=sys.stderr)
            failed += 1
    for old in sorted(p for p in DEST.iterdir() if p.is_dir())[:-KEEP]:
        shutil.rmtree(old)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
