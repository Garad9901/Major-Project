# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Ollama's own per-call timings, collected per thread.

WHY THIS EXISTS
`orchestrator/profiling.py` already times each pipeline stage with a wall clock,
and that was enough to establish which stage is slow. It is not enough to decide
what to DO about it, because a stage that takes 20 seconds can be 20 seconds of
any of these, and the fix is different in every case:

    queueing behind another request      -> admission control / concurrency
    loading the model into memory        -> keep-alive
    READING the prompt                   -> shorten the prompt
    GENERATING the answer                -> fewer output tokens, or a smaller
                                            model, or faster silicon

Guessing between those is how the previous latency pass ended up capping
`num_predict` on an agent that was not generating many tokens anyway. Ollama
reports the split itself, in nanoseconds, on every response:

    load_duration          time spent loading the model (0 when resident)
    prompt_eval_count      tokens READ
    prompt_eval_duration   time spent reading them
    eval_count             tokens GENERATED
    eval_duration          time spent generating them

This module captures those and hands them to whichever profiling stage is
currently running.

WHY A THREAD-LOCAL RATHER THAN A PARAMETER
The alternative is threading a profile object through six agent modules and
every function between them, purely so a timing can be recorded. The agents
would then all depend on the orchestrator's profiler, which is backwards.

A thread-local works here because every LLM call happens on the same thread as
the profiling stage that encloses it — the SQL and RAG branches each run whole
inside one pool worker (see orchestrator/service._run_sql), and the streaming
synthesis generator is consumed on the request thread. Anything running on a
thread nobody is collecting on simply records nothing, which is the correct
behaviour for management commands, tests and the sync worker.

COST
One `getattr` and one list append per LLM call, against calls measured in
seconds.
"""

import threading

_local = threading.local()


def _calls():
    return getattr(_local, "calls", None)


def start():
    """Begin collecting on this thread, discarding anything already buffered."""
    _local.calls = []


def stop():
    """Stop collecting on this thread. Calls made after this are dropped."""
    _local.calls = None


def take():
    """Return the calls recorded since the last take(), and reset the buffer.

    Returns [] when nothing was recorded, and also when collection was never
    started on this thread — the caller cannot tell the difference and does not
    need to.
    """
    calls = _calls()
    if not calls:
        return []
    _local.calls = []
    return calls


def record(label, model, response):
    """Record one Ollama call from its final JSON response object.

    `response` is the parsed body of a non-streaming /api/chat call, or the
    final `done` chunk of a streaming one — both carry the same timing fields.
    Silently does nothing when this thread is not collecting.

    Missing fields are tolerated. /api/embeddings returns no timings at all, and
    a future Ollama version could rename any of these; a profiler that raised on
    an unexpected payload would take the whole answer down with it.
    """
    calls = _calls()
    if calls is None:
        return
    if not isinstance(response, dict):
        response = {}

    def ms(key):
        value = response.get(key)
        # Ollama reports durations in NANOseconds.
        return round(value / 1e6, 1) if isinstance(value, (int, float)) else None

    calls.append({
        "label": label,
        "model": model,
        "load_ms": ms("load_duration"),
        "prompt_tokens": response.get("prompt_eval_count"),
        "prompt_ms": ms("prompt_eval_duration"),
        "gen_tokens": response.get("eval_count"),
        "gen_ms": ms("eval_duration"),
        "total_ms": ms("total_duration"),
    })


def summarise(calls):
    """Roll a list of recorded calls up into one dict of totals.

    Every value is a sum, including the token counts, because a single pipeline
    stage can make more than one call (verification makes two when it issues a
    correction). None is used for "nothing was recorded", which is different
    from a measured zero — a stage that made no LLM call at all must not report
    `prompt_tokens: 0` and be mistaken for one that read an empty prompt.
    """
    if not calls:
        return None
    out = {"llm_calls": len(calls)}
    for key in ("load_ms", "prompt_ms", "gen_ms", "prompt_tokens", "gen_tokens"):
        values = [c[key] for c in calls if c.get(key) is not None]
        out[key] = round(sum(values), 1) if values else None
    return out
