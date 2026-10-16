"""Task queue counts."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime

from hub import tasks


def collect(ctx: dict, now: datetime) -> dict:
    with closing(tasks.connect(ctx["tasks_db"])) as db:
        recent = [{"title": t["title"], "status": t["status"], "model": t["model"]}  # titles only, never prompts
                  for t in tasks.recent(db, limit=3)]
        return {**tasks.counts(db, now), "recent": recent}
