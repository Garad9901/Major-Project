# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Admission control for the local language model.

THE PROBLEM THIS SOLVES
Local CPU inference SERIALISES. Ollama answers roughly one question at a time;
a second concurrent generation does not run in parallel, it makes both slower
while competing for the same cores. Without admission control, twenty
simultaneous questions become twenty requests that each take twenty times as
long, every one of them eventually hitting a timeout. Everybody waits, nobody
is served, and the failure looks like a crash rather than a queue.

The rate limiter does NOT prevent this. A per-user limit of 10/min across 200
students permits 2,000 requests a minute at a server that can answer about
three. Rate limiting bounds one user's share; it says nothing about the total.

WHAT THIS DOES
Admits a bounded number of questions into the LLM pipeline at once and makes
everyone else wait briefly for a slot. If no slot frees up within the queue
timeout, the request is refused immediately with an honest "busy" message
instead of being accepted and left to hang.

A slot is held for the WHOLE pipeline, not per LLM call. One question makes
several calls (routing, SQL generation, synthesis); letting two questions
interleave their calls would make both slower for no gain in throughput.

WHY A PLAIN THREADING SEMAPHORE IS CORRECT HERE
It is process-local, so it only works if there is exactly one process serving
requests. Production runs GUNICORN_WORKERS=1 for precisely this reason (see
backend/gunicorn.conf.py). If the worker count is ever raised, this becomes a
per-worker limit and the effective concurrency becomes workers x
LLM_MAX_CONCURRENCY — at which point this needs to move to a shared store such
as Redis. That coupling is deliberate and is called out in DEPLOYMENT.md.
"""

import contextlib
import logging
import os
import threading

from common.exceptions import AssistantBusy

logger = logging.getLogger("orchestrator")

# How many questions may be in the LLM pipeline simultaneously.
# 1 is the honest default for CPU inference: the hardware cannot do two at once,
# so admitting two only splits the same cores. Raise ONLY with a GPU, and
# measure rather than guess.
MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "1"))

# How long a request waits for a slot before being told the assistant is busy.
# Long enough to absorb the tail of one in-flight answer, short enough that a
# refusal arrives while the user is still paying attention. Measured answers are
# 19-22s warm, so 25s covers roughly one full answer ahead in the queue.
QUEUE_TIMEOUT_SECONDS = float(os.getenv("LLM_QUEUE_TIMEOUT", "25"))

_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)

# Observability only — never used for control decisions, so a torn read is
# harmless. Reported in logs so an operator can see queueing before users complain.
_waiting = 0
_waiting_lock = threading.Lock()


def stats():
    """Current queue depth, for logging and the health endpoint."""
    return {
        "max_concurrency": MAX_CONCURRENCY,
        "waiting": _waiting,
        "queue_timeout_seconds": QUEUE_TIMEOUT_SECONDS,
    }


@contextlib.contextmanager
def llm_slot(label=""):
    """Hold one LLM slot for the duration of the block.

    Raises AssistantBusy if no slot becomes free within QUEUE_TIMEOUT_SECONDS.

    Release is in a `finally`, so it happens on success, on exception, and —
    when this wraps a generator — when the generator is closed because the
    client disconnected mid-stream. That last case relies on the generator being
    closed (explicitly or by garbage collection), which Django does for a
    StreamingHttpResponse whose client goes away.
    """
    global _waiting

    with _waiting_lock:
        _waiting += 1
        depth = _waiting

    if depth > MAX_CONCURRENCY:
        logger.info(
            "llm queue: %d waiting for %d slot(s) %s", depth, MAX_CONCURRENCY, label
        )

    try:
        acquired = _slots.acquire(timeout=QUEUE_TIMEOUT_SECONDS)
    finally:
        with _waiting_lock:
            _waiting -= 1

    if not acquired:
        logger.warning(
            "llm queue timeout after %.0fs (max_concurrency=%d) %s",
            QUEUE_TIMEOUT_SECONDS, MAX_CONCURRENCY, label,
        )
        raise AssistantBusy(
            f"no LLM slot available within {QUEUE_TIMEOUT_SECONDS:.0f}s"
        )

    try:
        yield
    finally:
        _slots.release()
