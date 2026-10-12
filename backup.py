#!/usr/bin/env python3
"""Daily consistent snapshot of the live SQLite DBs, gzip'd, keeping the last 7 days."""
import gzip
import shutil
import sqlite3
import sys
import tarfile
from datetime import date
from pathlib import Path

HOME = Path.home()
DBS = {"9router": HOME / "9router" / "data" / "db" / "data.sqlite", "hermes-state": HOME / ".hermes" / "state.db"}
DEST = HOME / "backups"
KEEP = 7
# Non-DB files 9router needs to come back with the same identity and logins.
ROUTER_FILES = ["docker-compose.yml", ".env", "data/jwt-secret", "data/machine-id", "data/auth"]


def snapshot(name: str, src: Path, day_dir: Path) -> Path:
    tmp = day_dir / f"{name}.sqlite"
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(tmp) as d:
        s.backup(d)
    out = tmp.with_suffix(".sqlite.gz")
    with open(tmp, "rb") as fi, gzip.open(out, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    tmp.unlink()
    verify(out)
    return out
def verify(gz: Path) -> None:
    """Restore the snapshot to a temp file and check it opens cleanly."""
    tmp = gz.with_suffix(".verify")
    try:
        with gzip.open(gz, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        # immutable: read without creating -wal/-shm files next to the copy
        with sqlite3.connect(f"file:{tmp}?immutable=1", uri=True) as db:
            result = db.execute("pragma quick_check").fetchone()[0]
        if result != "ok":
            raise sqlite3.DatabaseError(f"quick_check: {result}")
    finally:
        tmp.unlink(missing_ok=True)


def router_config(day_dir: Path) -> Path:
    out = day_dir / "9router-config.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for rel in ROUTER_FILES:
            tar.add(HOME / "9router" / rel, arcname=rel)
    out.chmod(0o600)
    with tarfile.open(out) as tar:  # verify: every file is readable back
        for member in tar.getmembers():
            if member.isfile():
                tar.extractfile(member).read()
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
    try:
        print(f"9router-config: {router_config(day_dir)}")
    except OSError as err:
        print(f"9router-config: GAGAL {err}", file=sys.stderr)
        failed += 1
    for old in sorted(p for p in DEST.iterdir() if p.is_dir())[:-KEEP]:
        shutil.rmtree(old)
    if failed:
        from digest import load_env  # only needed on failure
        from tg import send
        send(load_env(), f"<b>Backup VPS gagal</b> ({failed} item). Cek: journalctl -u db-backup")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
