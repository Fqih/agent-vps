#!/usr/bin/env python3
"""24/7 task worker: one task at a time through 9router, ntfy when done. Run: python3 -m hub.worker"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from digest import REPORT_DIR, load_env, model_config
from hub import notify, tasks
from hub.handlers import HANDLERS

POLL_SECONDS = 5
log = logging.getLogger("hub.worker")


def task_link(ctx: dict, task_id: int) -> str | None:
    base = ctx["env"].get("STATUS_PUBLIC_URL", "").rstrip("/")
    return f"{base}/task/{task_id}?token={ctx['env'].get('STATUS_TOKEN', '')}" if base else None


def run_once(db, ctx: dict, now: datetime | None = None) -> bool:
    task = tasks.claim(db, now)
    if task is None:
        return False
    title = task["payload"].get("title") or task["kind"]
    handler = HANDLERS.get(task["kind"])
    if handler is None:
        tasks.fail_now(db, task["id"], f"jenis tugas tidak dikenal: {task['kind']}", now)
        return True
    try:
        text, model = handler(task, ctx)
    except Exception as err:  # any handler error goes through the retry schedule
        log.warning("tugas #%s gagal: %s", task["id"], err)
        if tasks.retry_or_fail(db, task["id"], str(err), now) == "failed":
            notify.publish(ctx["env"], "tasks", f"Gagal: {title}", str(err)[:300],
                           click=task_link(ctx, task["id"]))
        return True
    tasks.finish(db, task["id"], text, model, now)
    if task["payload"].get("notify", True):
        notify.publish(ctx["env"], "tasks", f"Selesai: {title}", text[:400], click=task_link(ctx, task["id"]))
    return True


def main() -> None:
    logging.basicConfig(filename=REPORT_DIR / "hub-worker.log", level=logging.INFO,
                        format="[%(asctime)s] %(levelname)s %(name)s %(message)s")
    env = load_env()
    ctx = {"env": env, "cfg": model_config(env)}
    db = tasks.connect()
    log.info("worker jalan, %d tugas dikembalikan ke antrean", tasks.requeue_running(db))
    while True:
        try:
            if not run_once(db, ctx):
                time.sleep(POLL_SECONDS)
        except Exception:
            log.exception("worker loop error")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
