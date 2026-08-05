# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("sync_worker")

DB_CONFIG = {
    "host": os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres")),
    "port": os.getenv("RAG_AGENT_RO_PORT", os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("RAG_AGENT_RO_DB", os.getenv("POSTGRES_DB", "college_rag")),
    "user": os.getenv("RAG_AGENT_RO_USER", "rag_agent_ro"),
    "password": os.getenv("RAG_AGENT_RO_PASSWORD"),
    # Encrypted even on the internal network — see docker/Dockerfile.postgres.
    "sslmode": os.getenv("POSTGRES_SSLMODE", "require"),
}

POLL_INTERVAL_SECONDS = int(os.getenv("SYNC_WORKER_POLL_INTERVAL_SECONDS", "30"))

DATA_DIR = os.getenv("SYNC_WORKER_DATA_DIR", "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
QUEUE_FILE = os.path.join(DATA_DIR, "change_queue.jsonl")

# ==============================================================================
# WHICH TABLES TO POLL — discovered, not hard-coded
# ==============================================================================
# This module used to carry its own copy of the table allowlist: the third of
# three copies. The other two (the backend's setup_readonly_role command and
# sql_agent/schema.py) now share backend/common/allowlist.py.
#
# This worker CANNOT import that module — it runs in a separate container with
# its own build context, and no Python path reaches backend code from here.
#
# So rather than becoming a fourth copy, it asks the DATABASE what it may read.
# That is strictly stronger than importing a list: an imported list can drift
# from the grants actually in force, whereas this worker literally cannot poll a
# table Postgres has not granted it. The chain is:
#
#     common/allowlist.py  ->  setup_readonly_role  ->  Postgres grants  ->  here
#
# THE EXPLICIT EXCLUSION
# `courses_prerequisites` is granted to this role but must NOT be polled. It is
# a bare many-to-many join table (course_id, prerequisite_id) with no
# `updated_at` column, and change detection here rests entirely on comparing
# `updated_at` watermarks — polling it would raise UndefinedColumn every cycle.
# It stays granted because the SQL agent must JOIN through it to answer "what
# are the prerequisites for X".
#
# That exclusion is both enforced structurally (no watermark column -> cannot be
# polled) AND named below, so it is a documented decision rather than a silent
# side effect of the query. If the excluded set ever stops matching
# EXPECTED_EXCLUSIONS the worker says so loudly at startup, instead of quietly
# polling — or quietly skipping — something new.
# ==============================================================================

# The watermark column every pollable table must have.
WATERMARK_COLUMN = "updated_at"

# Documented, expected exclusions. This is an assertion aid only: changing it
# does not change behaviour, it changes whether the worker warns you.
#
#   courses_prerequisites
#       A bare many-to-many join table (course_id, prerequisite_id) with no
#       updated_at of its own. See the note above.
#
#   faculty_development
#       The imported 13,000-row survey snapshot. Deliberately built without an
#       updated_at column (see academics/models.FacultyDevelopment) so it is
#       excluded structurally rather than by a flag. It is bulk-loaded, static
#       between loads, and entirely numeric/categorical — polling it would queue
#       13,000 change events and embedding it would be 13,000 embedding calls
#       over rows containing no prose. Semantic search over that data is served
#       instead by faculty_development_profiles, which IS polled and embedded.
EXPECTED_EXCLUSIONS = {"courses_prerequisites", "faculty_development"}

_GRANTED_TABLES_SQL = """
    SELECT DISTINCT c.relname AS table_name
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_table_privilege(current_user, c.oid, 'SELECT')
    ORDER BY 1;
"""

_HAS_WATERMARK_SQL = """
    SELECT table_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND column_name = %s
      AND table_name = ANY(%s);
"""


def discover_tables(conn):
    """Returns (poll_tables, excluded) from live grants and schema.

    poll_tables — granted SELECT and has the watermark column.
    excluded    — granted SELECT but has no watermark column.
    """
    with conn.cursor() as cur:
        cur.execute(_GRANTED_TABLES_SQL)
        granted = [row[0] for row in cur.fetchall()]

        if not granted:
            raise RuntimeError(
                "This role has SELECT on no tables in schema 'public'. The "
                "backend's setup_readonly_role command issues those grants on "
                "startup — check that the backend came up cleanly."
            )

        cur.execute(_HAS_WATERMARK_SQL, (WATERMARK_COLUMN, granted))
        with_watermark = {row[0] for row in cur.fetchall()}

    poll_tables = [t for t in granted if t in with_watermark]
    excluded = sorted(t for t in granted if t not in with_watermark)
    return poll_tables, excluded


def log_discovery(poll_tables, excluded):
    """Reports what was discovered, and warns if the exclusions are not the ones
    this module documents."""
    logger.info(
        "discovered %d readable table(s) to poll: %s",
        len(poll_tables), ", ".join(poll_tables),
    )

    if excluded:
        logger.info(
            "excluded %d granted table(s) with no '%s' column: %s",
            len(excluded), WATERMARK_COLUMN, ", ".join(excluded),
        )

    unexpected = set(excluded) - EXPECTED_EXCLUSIONS
    missing = EXPECTED_EXCLUSIONS - set(excluded)

    if unexpected:
        logger.warning(
            "UNEXPECTED exclusion(s): %s — readable but with no '%s' column, so "
            "their changes will NEVER reach the search index. Either add the "
            "column or record them in EXPECTED_EXCLUSIONS.",
            ", ".join(sorted(unexpected)), WATERMARK_COLUMN,
        )
    if missing:
        logger.warning(
            "expected to exclude %s but did not — either the table gained an "
            "'%s' column (fine, it is now polled) or its grant was removed.",
            ", ".join(sorted(missing)), WATERMARK_COLUMN,
        )


# ==============================================================================
# WHICH TABLES TO EMBED
# ==============================================================================
# Not derivable from grants: an editorial judgement about which tables hold free
# text worth semantic search. The rest — rooms, schedules, timetables, fee
# amounts — are structured or numeric and are better answered by direct SQL than
# by a vector store, so they are never embedded.
#
# Intersected with the discovered poll list at runtime, so naming a table here
# that turns out not to be readable is harmless rather than a crash.
#
# faculty_development_profiles holds one prose paragraph per slice of the
# imported survey (per department, per rank, and so on). Its `body` column is
# the only genuinely free-text content that dataset has — and it is generated,
# not authored; see academics/models.FacultyDevelopmentProfile for exactly what
# that means and what it does not prove.
DESCRIPTIVE_TABLES = [
    "departments", "faculty", "programs", "courses",
    "faculty_development_profiles",
]

# How often to check for index entries whose source row has been DELETED.
# A watermark poll cannot observe an absence, so deletions need a separate pass
# — see reconcile_deletions() in main.py for what went wrong without it.
# 20 cycles x 30s is roughly every 10 minutes, plus once at every startup.
RECONCILE_EVERY_N_CYCLES = int(os.getenv("SYNC_WORKER_RECONCILE_EVERY_N_CYCLES", "20"))

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "college_docs")
