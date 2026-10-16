"""Active accounts per provider, read from the 9router DB."""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime

from hub.collectors.common import ro

SHORT = {"antigravity": "ag", "codex": "cx", "github": "gh"}


def collect(ctx: dict, now: datetime) -> dict:
    with closing(ro(ctx["router_db"])) as db:
        rows = db.execute("SELECT provider, data FROM providerConnections WHERE isActive = 1").fetchall()
    out = {}
    for provider, short in SHORT.items():
        states = [json.loads(data).get("testStatus") for p, data in rows if p == provider]
        if states:
            out[short] = f"{states.count('active')}/{len(states)}"
    return out
