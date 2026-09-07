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
#
# The intent is: long enough to absorb the tail of one in-flight answer, short
# enough that a refusal arrives while the user is still paying attention.
#
# 25 DOES NOT MEET THAT INTENT, and is kept only because what should replace it
# is a product decision about how long a student will wait, not an engineering
# one. This comment previously justified 25 as covering "one full answer ahead"
# on the basis of 19-22s warm answers. The measured end-to-end p50 over 163 real
# questions is 28.2s (docs/LATENCY.md), so the second person in the queue is
# refused BEFORE the answer ahead of them reaches its median completion.
#
# A 50-user load test recommended 120 (docs/SCALING.md), but measured only the
# coalescing-friendly shape -- 50 users over 5 shared questions, ~5 real
# generations. That does not establish 120 for a room asking different things.
#
# Operators should raise this. See docs/CAPACITY.md for how to measure it on
# your own hardware, which is the only place the number means anything.
QUEUE_TIMEOUT_SECONDS = float(os.getenv("LLM_QUEUE_TIMEOUT", "25"))

_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)

# ==============================================================================
# ADMISSION BOUND — why a queue timeout alone starves the deterministic path
# ==============================================================================
# gunicorn runs `gthread`: a request holds one worker THREAD for its whole life,
# and _slots.acquire(timeout=...) below BLOCKS while holding it. So a request
# waiting for the model is not merely waiting — it is occupying a thread that
# nothing else can use.
#
# With the shipped 4 threads, four model questions consumed every one, and a
# fast-path question that needs no model at all could not be served. Measured
# before this bound existed:
#
#     fast path, idle system            177 / 189 / 367 ms
#     fast path, 4 model requests live       17,173 ms      <- 47-97x
#
# 8s into the saturation + 17.2s waiting = 25.2s, which is exactly when three
# model requests hit the 25s queue timeout and returned their threads. THE FAST
# PATH WAS NOT WAITING FOR GENERATION. It was waiting for the queue timeout to
# expire, which means starvation scales with LLM_QUEUE_TIMEOUT rather than with
# how fast the model is.
#
# That inverts the recommendation in docs/SCALING.md to raise the timeout to
# 120: doing so without this bound would take starvation from 17s to 120s.
#
# THE FIX: cap how many threads model requests may occupy, and refuse the rest
# IMMEDIATELY rather than blocking. A refused request releases its thread in
# milliseconds, so threads beyond this bound are always available to the
# deterministic path no matter how deep the model queue is.
#
# Immediate refusal is also more honest than a slow one. A request that waits
# 25s to be told "busy" has consumed a thread for 25s to deliver no answer; the
# user would rather know at once, and the server would rather have the thread.
#
# SIZING: derived from GUNICORN_THREADS so the two cannot drift. Roughly a third
# of the pool may block on the model, leaving the rest for the fast path, the
# cache and health checks. With MAX_CONCURRENCY=1 only one of the admitted
# requests is generating anyway; the others are its queue.
_WORKER_THREADS = int(os.getenv("GUNICORN_THREADS", "4"))
MAX_ADMITTED = int(os.getenv("LLM_MAX_ADMITTED", str(max(1, _WORKER_THREADS // 3))))
_admission = threading.BoundedSemaphore(MAX_ADMITTED)

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

    # ADMISSION FIRST, AND WITHOUT BLOCKING.
    #
    # Held for the whole request, because it is the THREAD this protects, and
    # the thread is held until the response finishes streaming. Refusing here
    # costs microseconds and returns the thread immediately.
    if not _admission.acquire(blocking=False):
        with _waiting_lock:
            _waiting -= 1
        logger.info(
            "llm admission refused (%d already admitted, %d worker threads) %s",
            MAX_ADMITTED, _WORKER_THREADS, label,
        )
        raise AssistantBusy(
            f"the assistant is already handling {MAX_ADMITTED} questions"
        )

    try:
        acquired = _slots.acquire(timeout=QUEUE_TIMEOUT_SECONDS)
    except BaseException:
        _admission.release()
        raise
    finally:
        with _waiting_lock:
            _waiting -= 1

    if not acquired:
        _admission.release()
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
        _admission.release()
