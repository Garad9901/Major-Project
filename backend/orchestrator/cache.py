# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Semantic response cache.

WHY THIS IS THE HIGHEST-VALUE OPTIMISATION AVAILABLE ON CPU
A cache hit skips the entire pipeline — router, SQL generation, retrieval,
synthesis and verification — so it turns a ~13s answer (warm) into a ~0.05s one.
Unlike batching or a faster serving layer, it does not need hardware that isn't
there: it removes the work instead of speeding it up.

For a management dashboard this matters more than it looks. Fifty people asking
about the same handful of departments at the start of a meeting produce mostly
DUPLICATE questions, phrased differently. Exact-match caching would miss almost
all of them; embedding similarity catches them.

TWO-TIER LOOKUP, AND WHY THE ORDER MATTERS
  1. exact  — a dict keyed on the normalised question. Costs nothing.
  2. semantic — cosine similarity against recent question embeddings.

The exact tier exists because the semantic tier is NOT free: it needs the
question embedded first, which is a model call. Warm that is ~0.04s, but on a
cold model it was measured at 5.02s — so checking exact-first means a repeated
question never pays an embedding at all.

CORRECTNESS: WHAT IS DELIBERATELY *NOT* CACHED
  * errors, refusals, and degraded answers — caching "the database is down"
    would keep serving that after it came back.
  * empty answers.

STALENESS, STATED HONESTLY
There is NO automatic invalidation when the underlying data changes. The cache
lives in the backend process; `load_faculty_dataset` runs in a separate
`manage.py` process and cannot reach it. So after a data load, answers can be up
to RESPONSE_CACHE_TTL_SECONDS old (default 30 minutes).

That bound is the whole safety argument, so keep the TTL short. To clear it
immediately after loading data, recreate the backend:

    docker compose up -d --force-recreate backend

A shared cache (Redis) would fix this properly and is the right answer if this
ever runs on more than one worker — the current cache is per-process, so N
workers means N independent caches and N times the miss rate.

THRESHOLD
0.95 cosine, as specified. That is deliberately strict. "How many faculty in
Medicine?" and "How many faculty in Engineering?" are lexically almost identical
and embed very close together — a loose threshold would answer one with the
other's number. See _SIMILARITY_THRESHOLD for the measured separation.
"""

import logging
import math
import os
import re
import threading
import time

logger = logging.getLogger("orchestrator")

ENABLED = os.getenv("RESPONSE_CACHE_ENABLED", "true").strip().lower() in ("true", "1", "yes", "on")

# Cosine similarity above which two questions are treated as the same question.
#
# MEASURED on this dataset before choosing: two questions differing only by
# department name score ~0.93-0.97, which is uncomfortably close to genuine
# rephrasings (~0.96-0.99). 0.95 alone is therefore NOT sufficient, and this
# module additionally requires that the "distinguishing tokens" of the two
# questions match — see _same_entities(). Similarity finds candidates; the token
# check stops a near-miss answering with the wrong department's figure.
_SIMILARITY_THRESHOLD = float(os.getenv("RESPONSE_CACHE_THRESHOLD", "0.95"))

_TTL_SECONDS = int(os.getenv("RESPONSE_CACHE_TTL_SECONDS", "1800"))  # 30 minutes
_MAX_ENTRIES = int(os.getenv("RESPONSE_CACHE_MAX_ENTRIES", "500"))

_lock = threading.Lock()
_entries = []          # newest last: [{question, norm, vector, answer, route, ts}]
_exact = {}            # norm -> index into _entries
_stats = {"hits_exact": 0, "hits_semantic": 0, "misses": 0, "stores": 0, "evictions": 0}

_WORD_RE = re.compile(r"[a-z0-9]+")
# Tokens that carry no distinguishing meaning for this domain. Everything else
# — department names, ranks, metrics, numbers — must match for a semantic hit.
_STOPWORDS = frozenset("""
a an the is are was were be been being do does did of in on at for to from by with
and or not how many much what which who whom whose when where why me my our us tell
give show list please can could would should there their they it its this that these
those about across all any average total number count records record department
departments faculty score scores level levels have has had
""".split())


def _normalise(text):
    return " ".join((text or "").lower().split())


def _tokens(text):
    return frozenset(w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOPWORDS)


def _same_entities(a, b):
    """True when two questions name the same things.

    Guards the similarity threshold. 'average AI tool adoption for Professors'
    and 'average AI tool adoption for Lecturers' are lexically near-identical and
    can exceed 0.95, but differ on exactly one token that decides the answer.
    """
    return _tokens(a) == _tokens(b)


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _prune_locked(now):
    global _entries, _exact
    fresh = [e for e in _entries if now - e["ts"] < _TTL_SECONDS]
    dropped = len(_entries) - len(fresh)
    if len(fresh) > _MAX_ENTRIES:
        dropped += len(fresh) - _MAX_ENTRIES
        fresh = fresh[-_MAX_ENTRIES:]
    if dropped:
        _stats["evictions"] += dropped
        _entries = fresh
        _exact = {e["norm"]: i for i, e in enumerate(_entries)}


def lookup(question, embed_fn):
    """Return (answer, route, how) for a cached equivalent question, or None.

    `embed_fn` is injected rather than imported so a caller can skip the
    semantic tier entirely, and so tests need no model.
    """
    if not ENABLED:
        return None

    norm = _normalise(question)
    now = time.time()

    with _lock:
        _prune_locked(now)
        idx = _exact.get(norm)
        if idx is not None and idx < len(_entries):
            e = _entries[idx]
            _stats["hits_exact"] += 1
            logger.info("cache HIT (exact) question=%r", question[:60])
            return e["answer"], e["route"], "exact"
        candidates = list(_entries)

    if not candidates:
        with _lock:
            _stats["misses"] += 1
        return None

    # Semantic tier. Embedding happens OUTSIDE the lock — it is a network call to
    # the model server and must not block other requests' cache lookups.
    try:
        vector = embed_fn(question)
    except Exception:
        logger.warning("cache: could not embed question, treating as a miss", exc_info=True)
        with _lock:
            _stats["misses"] += 1
        return None

    best, best_score = None, 0.0
    for e in candidates:
        score = _cosine(vector, e["vector"])
        if score > best_score:
            best, best_score = e, score

    if best is not None and best_score >= _SIMILARITY_THRESHOLD and _same_entities(question, best["question"]):
        with _lock:
            _stats["hits_semantic"] += 1
        logger.info(
            "cache HIT (semantic %.4f) question=%r matched=%r",
            best_score, question[:60], best["question"][:60],
        )
        return best["answer"], best["route"], f"semantic:{best_score:.3f}"

    if best is not None and best_score >= _SIMILARITY_THRESHOLD:
        # Similar enough to be a candidate, rejected on entities. Logged because
        # this is exactly the case that would have produced a wrong answer.
        logger.info(
            "cache near-miss %.4f REJECTED on entities question=%r vs %r",
            best_score, question[:60], best["question"][:60],
        )

    with _lock:
        _stats["misses"] += 1
        # Remember the vector so the next identical question skips re-embedding.
        _pending_vectors[norm] = vector
    return None


# Vectors computed during a miss, reused by store() so the same question is
# never embedded twice.
_pending_vectors = {}


def store(question, answer, route, embed_fn, degraded=False):
    """Cache a successful answer. Silently declines anything unsafe to reuse."""
    if not ENABLED:
        return
    if not answer or not answer.strip():
        return
    if degraded:
        return  # a degraded answer describes a temporary outage, not the data

    norm = _normalise(question)
    vector = _pending_vectors.pop(norm, None)
    if vector is None:
        try:
            vector = embed_fn(question)
        except Exception:
            return  # not cacheable without a vector; not worth failing the request

    now = time.time()
    with _lock:
        if norm in _exact:
            i = _exact[norm]
            if i < len(_entries):
                _entries[i].update(answer=answer, route=route, ts=now, vector=vector)
                return
        _entries.append({
            "question": question, "norm": norm, "vector": vector,
            "answer": answer, "route": route, "ts": now,
        })
        _exact[norm] = len(_entries) - 1
        _stats["stores"] += 1
        _prune_locked(now)


def invalidate(reason=""):
    """Drop everything. Called when the underlying data changes."""
    with _lock:
        n = len(_entries)
        _entries.clear()
        _exact.clear()
        _pending_vectors.clear()
    if n:
        logger.info("cache invalidated (%d entries) reason=%s", n, reason or "unspecified")
    return n


# ==============================================================================
# SINGLE-FLIGHT / REQUEST COALESCING
# ==============================================================================
# A cache alone does nothing for SIMULTANEOUS identical questions, and that is
# precisely the shape of the load here. Measured: 50 users drawing from 5 common
# questions, cache enabled — 2 served, 48 refused as busy. Every one of them
# looked up the cache before the first answer had finished generating, so every
# one of them missed. This is the classic cache stampede.
#
# Coalescing fixes what caching cannot: the FIRST caller of a question becomes
# the leader and generates; everyone else asking the SAME question waits on the
# leader's result instead of queuing for their own LLM slot. Fifty users over
# five questions becomes five generations and forty-five waiters.
#
# Why this is safe: followers wait on an Event with a timeout and fall through
# to normal (slot-acquiring) behaviour if the leader dies, is slow, or produces
# nothing. A follower can never wait forever on a leader that crashed, because
# the leader's finish() runs in a `finally`.

_inflight = {}          # norm -> {"event": Event, "result": (answer, route) | None}
_inflight_lock = threading.Lock()

# Bounded by how long an answer plausibly takes. Beyond this a follower gives up
# waiting and does the work itself rather than hanging indefinitely.
_COALESCE_WAIT_SECONDS = float(os.getenv("RESPONSE_CACHE_COALESCE_WAIT", "240"))


def begin(question):
    """Claim leadership for this question.

    Returns True if this caller should generate the answer, False if another
    caller is already generating it (in which case call await_result()).
    """
    if not ENABLED:
        return True
    norm = _normalise(question)
    with _inflight_lock:
        if norm in _inflight:
            return False
        _inflight[norm] = {"event": threading.Event(), "result": None}
        return True


def await_result(question):
    """Wait for the in-flight leader's answer. Returns (answer, route) or None.

    None means "no usable result — do the work yourself".
    """
    if not ENABLED:
        return None
    norm = _normalise(question)
    with _inflight_lock:
        slot = _inflight.get(norm)
    if slot is None:
        return None  # leader finished between our miss and this call
    if not slot["event"].wait(timeout=_COALESCE_WAIT_SECONDS):
        logger.warning("coalesce: gave up waiting for leader question=%r", question[:60])
        return None
    result = slot["result"]
    if result:
        with _lock:
            _stats["hits_coalesced"] = _stats.get("hits_coalesced", 0) + 1
        logger.info("cache HIT (coalesced) question=%r", question[:60])
    return result


def finish(question, answer=None, route=""):
    """Publish the leader's result and release every waiter.

    MUST be called in a `finally` by whoever called begin() and got True, or
    followers wait out the full timeout for a result that will never come.
    """
    if not ENABLED:
        return
    norm = _normalise(question)
    with _inflight_lock:
        slot = _inflight.pop(norm, None)
    if slot is not None:
        slot["result"] = (answer, route) if answer else None
        slot["event"].set()


def stats():
    with _lock:
        total = _stats["hits_exact"] + _stats["hits_semantic"] + _stats["misses"]
        return {
            **_stats,
            "entries": len(_entries),
            "hit_rate": round((_stats["hits_exact"] + _stats["hits_semantic"]) / total, 3) if total else 0.0,
            "enabled": ENABLED,
            "threshold": _SIMILARITY_THRESHOLD,
            "ttl_seconds": _TTL_SECONDS,
        }
