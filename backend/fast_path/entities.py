# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The values a question may name, read from the database rather than listed.

WHY NOT A HARDCODED LIST OF DEPARTMENTS

Because the college's departments are not ours to know. A literal list works on
the demo data and is wrong on the first real deployment, and it would be wrong
SILENTLY — a question about a department missing from the list simply would not
match, fall through to the language model, and look like the fast path
"choosing" not to handle it. The failure would be invisible.

So the vocabulary comes from the same database the answer will come from. If
`departments` gains a row, the fast path can answer about it immediately, with
no code change and no redeploy.

WHY IT IS CACHED, AND WHY THE CACHE IS SHORT

Resolving a question must not cost a query per request — that would put the
database back on the critical path the fast path exists to clear. The values
change rarely (a new department is a yearly event), so they are cached in
process for CACHE_SECONDS.

The cache is deliberately NOT the answer cache in orchestrator/cache.py: that
one holds ANSWERS and is invalidated when records change. This holds VOCABULARY
and its staleness has a different consequence — a brand-new department is
briefly unmatched and the question goes to the language model, which is the
correct degradation rather than a wrong answer.

FAILURE IS NOT EMPTINESS

If the lookup fails, this returns None, and the caller treats that as "the fast
path is unavailable" rather than "there are no departments". An empty vocabulary
would silently disable matching, which is the shape of defect this project has
found four times now.
"""

import logging
import threading
import time

from common import schema_map

logger = logging.getLogger("fast_path")

CACHE_SECONDS = 300

_lock = threading.Lock()
_cache = {"at": 0.0, "values": None}

# The columns whose DISTINCT values a question may name, per logical table.
# Only low-cardinality descriptive columns belong here: these become the
# vocabulary the matcher looks for in a question, and a high-cardinality column
# would both be slow and match far too eagerly.
VOCABULARY_COLUMNS = {
    "faculty_development": [
        "department",
        "academic_rank",
        "competency_level",
        "university_type",
        "lms_usage_frequency",
        "target",
    ],
}


def _fetch(conn):
    values = {}
    cur = conn.cursor()
    try:
        for logical_table, columns in VOCABULARY_COLUMNS.items():
            table = schema_map.physical(logical_table, qualified=True)
            for column in columns:
                physical_column = schema_map.physical_column(logical_table, column)
                # The table and column names are NOT user input: they come from
                # the schema map, which is an allowlist. No value from the
                # question is ever interpolated into SQL anywhere in this
                # package — see queries.py.
                cur.execute(f"SELECT DISTINCT {physical_column} FROM {table}")
                found = [
                    str(row[0]).strip()
                    for row in cur.fetchall()
                    if row[0] is not None and str(row[0]).strip()
                ]
                if found:
                    values[(logical_table, column)] = found
    finally:
        try:
            cur.close()
        except Exception:
            pass
    return values


def vocabulary(conn_factory):
    """{(table, column): [values]}, or None when the lookup could not run.

    None means UNAVAILABLE, never "empty". The caller must not treat it as a
    vocabulary with nothing in it.
    """
    now = time.time()
    cached = _cache["values"]
    if cached is not None and (now - _cache["at"]) < CACHE_SECONDS:
        return cached

    try:
        with conn_factory() as conn:
            values = _fetch(conn)
    except Exception as exc:
        # Deliberately broad: any failure to read the vocabulary must disable
        # the fast path rather than produce a partial one. A partial vocabulary
        # would answer some questions and silently route others away, which is
        # indistinguishable from the fast path working.
        logger.warning("fast path vocabulary unavailable (%s) — deferring to the model", exc)
        return None

    if not values:
        logger.warning("fast path vocabulary came back empty — deferring to the model")
        return None

    with _lock:
        _cache["values"] = values
        _cache["at"] = now
    return values


def reset():
    """Drop the cached vocabulary. For tests and for a records import."""
    with _lock:
        _cache["values"] = None
        _cache["at"] = 0.0
