# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Pre-computed prose answers over bounded entity sets.

WHY
Descriptive questions are slow because a model writes them at request time -
measured p50 55 s on this hardware. But most of them are about bounded sets: 8
departments, 4 ranks, 4 competency levels, 3 university types. Generate those
answers in the background, verify them, store them, and serve them as lookups.
An 87-second question becomes a ~100 ms one. The model still runs - when nobody
is waiting, not while a person is.

WHAT IS PRE-COMPUTED - FROM EVIDENCE, NOT GUESSES
The shapes below were derived by replaying the audit log through the fast path
and collapsing entity names in what fell through: 265 requests over 114 distinct
questions. The department profile alone is ~39 of them across five phrasings.
Adversarial and unanswerable questions ("wifi password", prompt injections,
"who teaches maths") are not shapes and are not pre-computed.

Single-entity shapes are pre-computed for every entity. Pair shapes are NOT -
"compare X and Y" over 8 departments is 28 pairs, over 100 entities 4,950 -
so pairs are generated only when OBSERVED in traffic, with a hard cap of
PAIR_CAP. One pair has ever been asked here; 28 x 55 s would be 26 minutes of
first-run cost for no observed demand.

VERIFICATION MATTERS MORE HERE, NOT LESS
A wrong live answer is served once. A wrong stored answer is served hundreds of
times and carries the authority of being instant. So every answer is produced
by the FULL pipeline including verification, and one that is degraded or has
any flagged claim is NOT stored - the question falls through to the live path.
The cost of full verification is amortised over every future serve.

FRESHNESS
Each stored answer records a data-version fingerprint of the rows it was built
from (count + latest timestamp for its entity). The refresher recomputes
fingerprints; an entity whose fingerprint changed has its answer DELETED first
- so it is never served stale, the question goes live - and then regenerated,
subject to a debounce of MIN_REGEN_INTERVAL_S per entity so a table changing
constantly cannot trigger constant regeneration. An entity that has vanished
from the vocabulary has its answers deleted, not served.

Cross-process: the refresher watches the same cache generation token that
orchestrator/cache.py bumps when records change, so a sync or import that
invalidates the answer cache also triggers a fingerprint sweep here.
"""

import hashlib
import logging
import re
import threading
import time

from django.utils import timezone

from common import schema_map
from fast_path import entities as fp_entities

logger = logging.getLogger("orchestrator")

# Hard cap on pair-shape answers, and why: 28 possible department pairs at
# ~55 s each is 26 minutes of first-run generation for a shape asked 8 times in
# 886 requests, all for ONE pair. 6 is generous headroom over what has been
# observed while keeping the worst case under six minutes.
PAIR_CAP = 6

# An entity is regenerated at most this often, however many times its rows
# change in between. Between regenerations the question is served LIVE, not
# stale - the stored answer is deleted the moment the fingerprint moves.
MIN_REGEN_INTERVAL_S = 600

# Seconds an answer must take to be worth storing. Anything faster than this
# would have been the fast path; storing it buys nothing and risks staleness.
_MIN_WORTHWHILE_MS = 2000

_SOURCE_TABLE = "faculty_development"


class Shape:
    """One pre-computable question family.

    `pattern` recognises the family in a user's question; `slots` name the
    entity columns whose values fill it; `canonical` is the question the
    pipeline is actually asked, so every phrasing of the same family shares one
    stored answer.
    """

    def __init__(self, name, pattern, slots, canonical, weight, pair=False):
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.slots = slots          # [(table, column)], all on _SOURCE_TABLE
        self.canonical = canonical  # format with v0, v1...
        self.weight = weight        # observed requests, for generation order
        self.pair = pair

    def key(self, values):
        return "|".join(values)


_D = (_SOURCE_TABLE, "department")
_R = (_SOURCE_TABLE, "academic_rank")
_L = (_SOURCE_TABLE, "competency_level")
_U = (_SOURCE_TABLE, "university_type")

SHAPES = [
    Shape(
        "department_profile",
        r"(describe|overview|profile|summar|how .* doing|development needs?)"
        r".*\bdepartment\b|"
        r"\bdepartment\b.*(describe|overview|profile|summar|doing|development needs?)|"
        r"how many faculty .* and describe",
        [_D],
        "Describe the faculty development profile for the {v0} department.",
        weight=39,
    ),
    Shape(
        "rank_digital_readiness",
        r"(digital readiness|digital capabilit|digitally).*\b(professor|lecturer)",
        [_R],
        "Summarise the digital readiness of {v0}s.",
        weight=8,
    ),
    Shape(
        "rank_research_output",
        r"research output.*\b(professor|lecturer)|\b(professor|lecturer)s?\b.*research output",
        [_R],
        "Describe the research output of {v0}s.",
        weight=8,
    ),
    Shape(
        "competency_overview",
        r"(overview|describe|summar|profile).*\bcompetenc",
        [_L],
        "Give an overview of faculty with {v0} competency.",
        weight=8,
    ),
    Shape(
        "university_type_profile",
        r"(profile|describe|overview|summar|say about).*\buniversit",
        [_U],
        "What does the profile say about {v0} university faculty?",
        weight=8,
    ),
    Shape(
        "departments_strongest_digital",
        r"which departments?.*(strongest|best|leading).*digital",
        [],
        "Which departments would you characterise as strongest at digital teaching?",
        weight=10,
    ),
    Shape(
        "lms_usage_meaning",
        r"lms.*(suggest|mean|imply)",
        [],
        "How many faculty use the LMS frequently, and what does that suggest?",
        weight=7,
    ),
    Shape(
        "department_compare",
        r"\bcompare\b.*\bdepartment|\bcompare\b.*\band\b.*(faculty|development)",
        [_D, _D],
        "Compare {v0} and {v1} faculty development.",
        weight=8,
        pair=True,
    ),
]
SHAPES.sort(key=lambda s: -s.weight)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _find_values(question, slots, vocab):
    """Resolve slot values from the DATABASE vocabulary, longest first, on word
    boundaries, allowing a plural 's' ("Assistant Professors").

    Same rules as fast_path._find_values, for the same reasons: "Science" must
    not be found inside "Computer Science", and "Arts" not inside "Martial
    Arts". Substring matching has bitten this codebase three times.
    """
    lowered = question.lower()
    values, consumed = [], []
    for table, column in slots:
        candidates = vocab.get((table, column))
        if not candidates:
            return None
        best = None
        for cand in sorted(candidates, key=len, reverse=True):
            for m in re.finditer(rf"\b{re.escape(cand.lower())}s?\b", lowered):
                span = (m.start(), m.end())
                if any(span[0] < e and s < span[1] for s, e in consumed):
                    continue
                best = (cand, span)
                break
            if best:
                break
        if best is None:
            return None
        values.append(best[0])
        consumed.append(best[1])
    return values


def match(question, conn_factory):
    """(shape, values) for a pre-computable question, else None."""
    if not question or not question.strip():
        return None
    vocab = fp_entities.vocabulary(conn_factory)
    if vocab is None:
        return None
    for shape in SHAPES:
        if not shape.pattern.search(question):
            continue
        values = _find_values(question, shape.slots, vocab)
        if values is None:
            continue
        if shape.pair and values[0] == values[1]:
            continue  # "compare Engineering and Engineering" is not a pair
        return shape, values
    return None


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------

def fingerprint(values_by_column, conn_factory):
    """A version token for the rows an answer depends on.

    count + latest load timestamp for the entity's rows. Cheap (indexed
    aggregate), and any insert, delete or reload of those rows moves it. Column
    and table names come from the schema map; only VALUES are bound.
    Returns None if the lookup fails - and None never equals a stored version,
    so a failure reads as "changed", which regenerates rather than serving
    something whose freshness is unknown.
    """
    table = schema_map.physical(_SOURCE_TABLE, qualified=True)
    where, params = [], []
    for column, value in values_by_column:
        where.append(f"{schema_map.physical_column(_SOURCE_TABLE, column)} = {{p}}")
        params.append(value)
    sql = f"SELECT COUNT(*), MAX(loaded_at) FROM {table}"
    if where:
        sql += " WHERE " + " OR ".join(where)  # pairs: rows of EITHER entity
    try:
        with conn_factory() as conn:
            ph = "?" if "pyodbc" in (type(conn).__module__ or "") else "%s"
            cur = conn.cursor()
            try:
                cur.execute(sql.replace("{p}", ph), tuple(params))
                count, latest = cur.fetchone()
            finally:
                cur.close()
    except Exception as exc:
        logger.warning("precompute fingerprint failed (%s)", exc)
        return None
    return hashlib.sha256(f"{count}|{latest}".encode()).hexdigest()[:24]


def _slot_pairs(shape, values):
    return [(col, val) for (_t, col), val in zip(shape.slots, values)]


# ---------------------------------------------------------------------------
# Generate + verify + store
# ---------------------------------------------------------------------------

def _verified(result):
    """True only when the pipeline produced a clean, fully-checked answer."""
    if result.get("degraded"):
        return False
    v = result.get("verification") or {}
    if v.get("verification") != "ran":
        return False
    if v.get("claims_flagged"):
        return False
    return True


def generate(shape, values, conn_factory, reason=""):
    """Run the FULL pipeline for the canonical question; store only if verified.

    Returns (stored: bool, detail: str). Takes the LLM slot like any request,
    so callers decide WHEN - the refresher only calls this when nobody is
    waiting (concurrency.queue_position() == 1).
    """
    from . import service
    from .models import PrecomputedAnswer

    question = shape.canonical.format(**{f"v{i}": v for i, v in enumerate(values)})
    version = fingerprint(_slot_pairs(shape, values), conn_factory)
    started = time.perf_counter()
    try:
        result = service.answer_question(question)
    except Exception as exc:
        return False, f"pipeline error: {exc}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if not _verified(result):
        v = result.get("verification") or {}
        detail = (
            f"NOT stored: degraded={result.get('degraded')} "
            f"verification={v.get('verification')} flagged={v.get('claims_flagged')}"
        )
        logger.warning("precompute %s %s %s", shape.name, values, detail)
        # A previously stored answer for this key must not outlive a failed
        # regeneration: delete it so the question goes live rather than stale.
        PrecomputedAnswer.objects.filter(shape=shape.name, entity_key=shape.key(values)).delete()
        return False, detail

    PrecomputedAnswer.objects.update_or_create(
        shape=shape.name,
        entity_key=shape.key(values),
        defaults={
            "canonical_question": question,
            "answer": result["answer"],
            "route": result.get("route") or "",
            "sources": {"sql": result.get("sql"), "rag": result.get("rag"), "web": result.get("web")},
            "verification": result.get("verification") or {},
            "data_version": version or "",
            "generation_ms": elapsed_ms,
            "generated_at": timezone.now(),
        },
    )
    logger.info("precompute stored %s %s in %d ms (%s)", shape.name, values, elapsed_ms, reason or "manual")
    return True, f"stored in {elapsed_ms} ms"


# ---------------------------------------------------------------------------
# Planning: what SHOULD exist, in priority order
# ---------------------------------------------------------------------------

def plan(conn_factory, observed_pairs=None):
    """[(shape, values)] for every answer that should be stored, by weight.

    Singles: every value of every slot. Pairs: only those observed in traffic,
    capped at PAIR_CAP. `observed_pairs` is {shape_name: [(v0, v1), ...]}.
    """
    vocab = fp_entities.vocabulary(conn_factory) or {}
    items = []
    for shape in SHAPES:
        if shape.pair:
            pairs = (observed_pairs or {}).get(shape.name, [])[:PAIR_CAP]
            for v0, v1 in pairs:
                items.append((shape, [v0, v1]))
            continue
        if not shape.slots:
            items.append((shape, []))
            continue
        table, column = shape.slots[0]
        for value in vocab.get((table, column), []):
            items.append((shape, [value]))
    return items


def observed_pairs_from_audit():
    """Pairs actually asked, from the audit log, most frequent first."""
    from audit.models import AuditLog
    from sql_agent import db

    vocab = fp_entities.vocabulary(db.connection) or {}
    out = {}
    for shape in SHAPES:
        if not shape.pair:
            continue
        counts = {}
        for q in AuditLog.objects.filter(route__in=("RAG", "BOTH", "SQL")).values_list("question", flat=True):
            if not shape.pattern.search(q or ""):
                continue
            vals = _find_values(q, shape.slots, vocab)
            if vals and vals[0] != vals[1]:
                k = tuple(vals)
                counts[k] = counts.get(k, 0) + 1
        out[shape.name] = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    return out


def projected_first_run(items, p50_seconds):
    """Seconds the initial generation is expected to take. Reported BEFORE
    starting so nobody thinks an install has hung."""
    return int(len(items) * p50_seconds)


# ---------------------------------------------------------------------------
# Refresh: fingerprints, deletion, debounced regeneration
# ---------------------------------------------------------------------------

def refresh(conn_factory, only_when_idle=True, budget_s=None, reason="refresh"):
    """Bring the store in line with the data. Returns a summary dict.

    1. every stored answer whose fingerprint moved is DELETED at once
    2. every stored answer whose entity vanished from the vocabulary is deleted
    3. missing answers are generated by weight, skipping any entity generated
       within MIN_REGEN_INTERVAL_S, and only while nobody is waiting for the
       model (unless only_when_idle=False, e.g. the install-time command)
    """
    from . import concurrency
    from .models import PrecomputedAnswer

    # No close_old_connections() here: that is the long-lived refresher
    # thread's responsibility (precompute_refresher._loop), and calling it
    # inside a Django TestCase closes the test transaction under the caller.
    summary = {"deleted_changed": 0, "deleted_gone": 0, "generated": 0,
               "rejected": 0, "debounced": 0, "skipped_busy": 0}
    started = time.time()

    wanted = plan(conn_factory, observed_pairs_from_audit())
    wanted_keys = {(s.name, s.key(v)) for s, v in wanted}
    by_name = {s.name: s for s in SHAPES}

    # 1 + 2: prune
    for stored in list(PrecomputedAnswer.objects.all()):
        key = (stored.shape, stored.entity_key)
        shape = by_name.get(stored.shape)
        if shape is None or key not in wanted_keys:
            stored.delete()
            summary["deleted_gone"] += 1
            continue
        values = stored.entity_key.split("|") if stored.entity_key else []
        current = fingerprint(_slot_pairs(shape, values), conn_factory)
        if current != stored.data_version:
            logger.info("precompute %s %s changed (%s -> %s): deleting",
                        shape.name, values, stored.data_version[:8], (current or "?")[:8])
            stored.delete()
            summary["deleted_changed"] += 1

    # 3: fill, debounced, idle-only
    existing = {(p.shape, p.entity_key): p for p in PrecomputedAnswer.objects.all()}
    recent = _recent_generations()
    for shape, values in wanted:
        key = (shape.name, shape.key(values))
        if key in existing:
            continue
        if budget_s is not None and time.time() - started > budget_s:
            break
        last = recent.get(key)
        if last and time.time() - last < MIN_REGEN_INTERVAL_S:
            summary["debounced"] += 1
            continue
        if only_when_idle and concurrency.queue_position() > 1:
            summary["skipped_busy"] += 1
            continue
        _recent_generations()[key] = time.time()
        stored, _detail = generate(shape, values, conn_factory, reason=reason)
        summary["generated" if stored else "rejected"] += 1
    return summary


_recent = {}
_recent_lock = threading.Lock()


def _recent_generations():
    """Process-local record of when each key was last attempted.

    Process-local is enough: with GUNICORN_WORKERS=1 there is one refresher.
    If workers are ever raised this must move to Redis, the same way the
    cache generation did (see orchestrator/cache.py for why).
    """
    return _recent


# ---------------------------------------------------------------------------
# Lookup, for the request path
# ---------------------------------------------------------------------------

def lookup(question, conn_factory):
    """A stored, verified answer for this question, or None."""
    from .models import PrecomputedAnswer

    found = match(question, conn_factory)
    if found is None:
        return None
    shape, values = found
    try:
        return PrecomputedAnswer.objects.filter(shape=shape.name, entity_key=shape.key(values)).first()
    except Exception as exc:
        logger.warning("precompute lookup failed (%s)", exc)
        return None
