# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Background thread that keeps the pre-computed answers fresh and complete.

Started once per gunicorn worker from gunicorn.conf.py's post_worker_init.
With GUNICORN_WORKERS=1 that is once per process, which is the same reason the
LLM semaphore is process-local (see orchestrator/concurrency.py).

WHAT IT DOES, EVERY TICK
  1. If the answer-cache generation token has moved since the last tick -
     which is what a records import or the sync worker bumps - run a full
     fingerprint sweep: delete changed and vanished answers, regenerate them.
  2. Otherwise, if anything planned is missing, generate ONE of it.

WHEN IT RUNS THE MODEL
Only when nobody is waiting: precompute.refresh() checks
concurrency.queue_position() before each generation and skips if anyone is
queued. A person's question always wins over background work. The cost is that
on a busy server the store fills slowly; the alternative - competing with users
for the single slot - is exactly what pre-computation exists to prevent.

DEBOUNCE
precompute.MIN_REGEN_INTERVAL_S (600 s) per entity, enforced inside refresh().
A table that changes every few seconds triggers a fingerprint sweep every tick
(cheap: one indexed aggregate per stored answer) but regenerates each entity at
most once per ten minutes. Between regenerations that entity's stored answer
has already been deleted, so its questions are answered live - slower, never
stale.
"""

import logging
import os
import threading
import time

logger = logging.getLogger("orchestrator")

TICK_SECONDS = int(os.getenv("PRECOMPUTE_TICK_SECONDS", "60"))
ENABLED = os.getenv("PRECOMPUTE_BACKGROUND", "true").strip().lower() in ("1", "true", "yes", "on")

_thread = None
_stop = threading.Event()


def _conn_factory():
    from sql_agent import db, db_mssql, guard
    return (db_mssql if guard.DIALECT == "tsql" else db).connection


def _loop():
    from django.db import close_old_connections

    from . import cache, precompute

    last_generation = None
    # First tick is delayed so the worker finishes warming and the health check
    # sees "ready" before any background model work starts.
    _stop.wait(TICK_SECONDS)
    while not _stop.is_set():
        try:
            close_old_connections()
            current = cache.current_generation()
            changed = current is not None and current != last_generation
            if changed and last_generation is not None:
                logger.info("precompute refresher: cache generation moved - sweeping fingerprints")
                summary = precompute.refresh(_conn_factory(), only_when_idle=True, reason="generation moved")
                logger.info("precompute refresher: %s", summary)
            else:
                # Fill at most one missing answer per tick, so a long first run
                # is spread across idle moments rather than monopolising them.
                summary = precompute.refresh(_conn_factory(), only_when_idle=True,
                                             budget_s=1, reason="background fill")
                if summary.get("generated") or summary.get("rejected"):
                    logger.info("precompute refresher: %s", summary)
            last_generation = current
        except Exception:
            logger.exception("precompute refresher tick failed")
        _stop.wait(TICK_SECONDS)


def start():
    """Idempotent. Safe to call from a gunicorn hook or a test."""
    global _thread
    if not ENABLED:
        logger.info("precompute refresher disabled (PRECOMPUTE_BACKGROUND)")
        return None
    if _thread is not None and _thread.is_alive():
        return _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="precompute-refresher", daemon=True)
    _thread.start()
    logger.info("precompute refresher started (tick=%ss)", TICK_SECONDS)
    return _thread


def stop():
    _stop.set()
