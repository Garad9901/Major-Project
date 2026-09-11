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
# 120, RAISED FROM 25 - and safe to raise only now, for two reasons that both
# had to land first.
#
# 1. The wait is VISIBLE. _generate_stream sends a "queued" stage with the
#    exact position and an estimate before entering the slot. A 120-second wait
#    against a blank screen is a hang; against "2nd in line, about 90 seconds"
#    it is information, and the person can choose to give up. 25 was held for
#    as long as the wait was invisible - the comment here used to say the
#    replacement was a product decision about how long a student will wait,
#    and it stopped being a hard one once the student can see where they are.
#
# 2. Starvation no longer scales with this value. Before the admission bound,
#    a waiting request held a worker thread, so raising this from 25 to 120
#    would have taken fast-path starvation from 17 s to 120 s (docs/SCALING.md,
#    Phase 1). With the bound, threads beyond MAX_ADMITTED are never held by
#    waiters, and the deterministic path is unaffected by this number.
#
# Why 120 and not more: the measured model-path p50 is ~37-79 s by route
# (query_profile). 120 covers positions 1-3 at the SQL p50 and position 2 at
# the RAG p50; beyond that a wait exceeds what the estimate can make
# reasonable. docs/SCALING.md's 50-user test measured 120 as the value at which
# refusals stopped, on the coalescing-friendly shape.
QUEUE_TIMEOUT_SECONDS = float(os.getenv("LLM_QUEUE_TIMEOUT", "120"))

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
# SIZING - derived from what admission actually governs, which is NOT the
# thread count.
#
# The first version used GUNICORN_THREADS // 3 = 8. That is the wrong quantity.
# Thread count bounds how many requests can be HELD; it says nothing about how
# many can be SERVED. With MAX_CONCURRENCY=1 the queue is strictly serial, so a
# request at position k waits roughly (k-1) x p50 seconds:
#
#     position 1   waits  0 s    -> served
#     position 2   waits  ~p50   -> refused if p50 > LLM_QUEUE_TIMEOUT
#
# So admitting 8 against a 25 s timeout and a ~40 s p50 means 7 people each
# hold a thread for 25 s and are refused anyway. They were never servable.
# That is the exact cost this bound exists to remove, just smaller - and
# invisible, because the refusal message reads the same either way.
#
# Derivation:
#
#     MAX_ADMITTED = ceil(LLM_QUEUE_TIMEOUT / p50_answer_seconds) + 1
#
# i.e. everyone who could plausibly be reached before the timeout, plus one so
# the queue never sits empty while an answer is finishing. 25 s / ~40 s -> 2.
# 120 s / ~40 s -> 4. GUNICORN_THREADS remains a strict CEILING (the margin is
# what keeps the fast path unblockable) but is no longer the derivation.
#
# p50 COMES FROM MEASUREMENT, NOT A CONSTANT. It is read from query_profile -
# the model-path answers this deployment has actually produced - with a
# fallback only when no measurement exists yet. Pre-computation will move it,
# so it is recomputed via recompute_admission() rather than fixed at import.
_WORKER_THREADS = int(os.getenv("GUNICORN_THREADS", "4"))

# Used only when query_profile has no model-path rows yet (a fresh install).
# 87 is the p50 recorded in docs/PRODUCT_PLAN.md for the reference hardware.
_FALLBACK_P50_SECONDS = float(os.getenv("LLM_P50_SECONDS", "87"))

# How many recent model-path answers the p50 is taken over. Enough to be
# stable, few enough to follow a real change within a day of normal use.
_P50_SAMPLE = 200


def measured_model_p50_seconds():
    """p50 of recent model-path answers, or None if it cannot be measured.

    Model-path means anything the model produced: FAST and PRECOMPUTED are
    excluded because they do not occupy the slot this bound governs, and cached
    answers are excluded because they did not occupy it either.

    Returns None rather than a default on any failure, so the caller can say
    which it used. A number that quietly came from a constant would defeat the
    point of measuring.
    """
    try:
        from .models import QueryProfile  # local: this module loads before apps

        rows = list(
            QueryProfile.objects.filter(cached="")
            .exclude(route__in=("FAST", "PRECOMPUTED", ""))
            .order_by("-id")
            .values_list("total_ms", flat=True)[:_P50_SAMPLE]
        )
    except Exception:  # database not up yet, table absent, etc.
        return None
    rows = sorted(v for v in rows if v is not None)
    if len(rows) < 5:  # too few to call it a median
        return None
    return rows[len(rows) // 2] / 1000.0


def derive_max_admitted(queue_timeout_s, p50_s, worker_threads):
    """ceil(timeout / p50) + 1, capped strictly below the thread count."""
    import math

    p50_s = max(float(p50_s), 0.001)
    derived = math.ceil(queue_timeout_s / p50_s) + 1
    ceiling = max(1, worker_threads - 1)
    return max(1, min(derived, ceiling))


# RLock, NOT Lock. _get_admission() holds this while calling
# recompute_admission(), which takes it again. With a plain Lock that is a
# deadlock on the FIRST llm_slot() of the process - i.e. the first model
# request after every deploy. The unit tests missed it because they call
# recompute_admission() directly; the full suite caught it by hanging for ten
# minutes at the first orchestrator test that entered the slot.
_admission_lock = threading.RLock()
_admission = None          # created lazily: needs the database for p50
MAX_ADMITTED = None
ADMISSION_SOURCE = None    # "measured" | "fallback" | "override", for stats()


def recompute_admission():
    """(Re)size the admission bound from the current measured p50.

    Safe to call while requests are in flight: each request captured the
    semaphore it acquired and releases THAT one, so swapping the module-level
    reference cannot double-release or strand a ticket.
    """
    global _admission, MAX_ADMITTED, ADMISSION_SOURCE
    override = os.getenv("LLM_MAX_ADMITTED", "").strip()
    if override:
        value, source, p50 = int(override), "override", None
    else:
        p50 = measured_model_p50_seconds()
        if p50 is None:
            p50, source = _FALLBACK_P50_SECONDS, "fallback"
        else:
            source = "measured"
        value = derive_max_admitted(QUEUE_TIMEOUT_SECONDS, p50, _WORKER_THREADS)
    with _admission_lock:
        _admission = threading.BoundedSemaphore(value)
        MAX_ADMITTED = value
        ADMISSION_SOURCE = source
    logger.info(
        "llm admission bound = %d (%s; p50=%s s, timeout=%.0f s, threads=%d)",
        value, source, ("%.1f" % p50) if p50 is not None else "n/a",
        QUEUE_TIMEOUT_SECONDS, _WORKER_THREADS,
    )
    return value


def _get_admission():
    if _admission is None:
        with _admission_lock:
            if _admission is None:
                recompute_admission()
    return _admission

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
        "max_admitted": MAX_ADMITTED,
        "admission_source": ADMISSION_SOURCE,
    }


def queue_position():
    """1-based position a request entering now would take. 1 means 'next'.

    Counts BOTH the requests waiting for a slot and the ones currently holding
    one. _waiting alone is not enough: it is decremented the moment a request
    acquires the slot, so with one answer generating and nobody queued it reads
    0 - and a newcomer is 2nd in line, not 1st. Caught by test_position_counts_
    everyone_ahead.

    _slots._value is the number of FREE slots; MAX_CONCURRENCY minus that is how
    many are held. Reading a semaphore's counter is an observability read, the
    same class as _waiting - never used for a control decision.

    The web layer shows this so a long wait is information, not a blank screen.
    """
    holding = MAX_CONCURRENCY - _slots._value
    return _waiting + holding + 1


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
    admission = _get_admission()
    if not admission.acquire(blocking=False):
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
        admission.release()
        raise
    finally:
        with _waiting_lock:
            _waiting -= 1

    if not acquired:
        admission.release()
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
        admission.release()
