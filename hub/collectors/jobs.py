"""Job pipeline counts from the tracker (state.sqlite)."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta

from hub.collectors.common import ro


def collect(ctx: dict, now: datetime) -> dict:
    with closing(ro(ctx["state_db"])) as db:
        def count(where: str, *args) -> int:
            return db.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}", args).fetchone()[0]
        since = (now - timedelta(days=1)).isoformat()
        top = db.execute("SELECT title, company FROM jobs WHERE status = 'baru' AND created_at >= ? "
                         "ORDER BY created_at DESC LIMIT 3", (since,)).fetchall()
        return {
            "top_new": [{"title": t or "?", "company": c or "?"} for t, c in top],
            "new_matches": count("status = 'baru' AND created_at >= ?", since),
            "drafts": 0,  # filled by the job-application agent (sub-project 1)
            "active": count("status IN ('disimpan', 'dilamar', 'interview')"),
            "interview": count("status = 'interview'"),
            "followup_due": count("status IN ('dilamar', 'interview') AND next_remind <= ?", now.isoformat()),
        }
