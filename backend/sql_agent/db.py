# Copyright (c) 2026 Yash Garad. All rights reserved.

import contextlib
import logging
import os
import threading

import psycopg2
import psycopg2.pool

from common import env
from common.exceptions import DatabaseUnavailable

logger = logging.getLogger("sql_agent")

# Deliberately NOT Django's own DB connection (that's the app-owner user).
# The SQL agent — both for schema introspection and for running
# LLM-generated queries — only ever connects as rag_agent_ro, so a bug here
# can't do more than that role's grants allow (see db/sql/create_rag_agent_ro.sql).
RAG_AGENT_RO_CONFIG = {
    # env_chain (common/env.py): a RAG_AGENT_RO_* value that is set but BLANK
    # (Docker Compose's `${RAG_AGENT_RO_HOST:-}` shape) now falls through to
    # POSTGRES_HOST/PORT/DB, same as an unset one. The nested os.getenv() this
    # replaced did not — a blanked-out override resolved to "" and the inner
    # fallback was never consulted, turning "I don't need a separate one" into
    # a DNS-lookup failure against an empty hostname.
    "host": env.env_chain("RAG_AGENT_RO_HOST", "POSTGRES_HOST", default="postgres"),
    "port": env.env_chain("RAG_AGENT_RO_PORT", "POSTGRES_PORT", default="5432"),
    "dbname": env.env_chain("RAG_AGENT_RO_DB", "POSTGRES_DB", default="college_rag"),
    "user": env.env_or("RAG_AGENT_RO_USER", "rag_agent_ro"),
    "password": os.getenv("RAG_AGENT_RO_PASSWORD"),
    # Encrypted even though this is an internal bridge: every row this
    # connection returns is institutional data. See docker/Dockerfile.postgres.
    "sslmode": env.env_or("POSTGRES_SSLMODE", "require"),
}

CONNECT_TIMEOUT_S = int(os.getenv("RAG_AGENT_RO_CONNECT_TIMEOUT", "5"))

# ==============================================================================
# CONNECTION POOL — and why it is NOT about latency
# ==============================================================================
# Profiling this pipeline showed connecting costs 0.01s and executing an agent
# query 0.00s. The database is nowhere near the bottleneck, so pooling buys no
# measurable speed. It is here for a different reason: a HARD CEILING.
#
#     rag_agent_ro has CONNECTION LIMIT 10   (set by setup_readonly_role)
#
# and answering ONE question opened TWO fresh connections — one to introspect
# the schema for the prompt, one to run the generated query. Under real
# concurrency that is 2xN connections against a limit of 10, so past about five
# simultaneous questions Postgres refuses with "too many connections for role".
# The failure mode is errors, not slowness — which is why the profile did not
# reveal it and a load test does.
#
# SIZING: the limit of 10 is SHARED with the sync worker, which holds one
# connection continuously. A max of 8 leaves that plus a spare for an operator
# running check_rag_agent_ro. If you raise this, raise the role's CONNECTION
# LIMIT first or you have simply moved where the error happens.
POOL_MIN = int(os.getenv("RAG_AGENT_RO_POOL_MIN", "1"))
POOL_MAX = int(os.getenv("RAG_AGENT_RO_POOL_MAX", "8"))

_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    """Create the pool on first use.

    Lazily, not at import time: the backend can start before Postgres is
    accepting connections, and an import-time failure would stop the module
    loading at all rather than producing a clean DatabaseUnavailable later.
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            try:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    POOL_MIN, POOL_MAX,
                    connect_timeout=CONNECT_TIMEOUT_S,
                    **RAG_AGENT_RO_CONFIG,
                )
                logger.info(
                    "rag_agent_ro connection pool ready (min=%d max=%d)", POOL_MIN, POOL_MAX
                )
            except psycopg2.OperationalError as exc:
                raise DatabaseUnavailable(f"could not connect to database: {exc}") from exc
    return _pool


@contextlib.contextmanager
def connection():
    """Borrow a pooled rag_agent_ro connection; always give it back.

    A connection that raised is returned with close=True so a broken socket is
    discarded rather than handed to the next caller — otherwise a single network
    blip would poison one pool slot for the life of the process.
    """
    pool = _get_pool()
    try:
        conn = pool.getconn()
    except psycopg2.pool.PoolError as exc:
        # Pool exhausted. Raised as DatabaseUnavailable so the orchestrator
        # degrades gracefully instead of leaking a raw psycopg2 error to a user.
        raise DatabaseUnavailable(f"no free database connection: {exc}") from exc
    except psycopg2.OperationalError as exc:
        raise DatabaseUnavailable(f"could not connect to database: {exc}") from exc

    broken = False
    try:
        yield conn
    except psycopg2.Error:
        broken = True
        raise
    finally:
        try:
            # The role is default_transaction_read_only, but psycopg2 still opens
            # a transaction — roll it back so the next borrower starts clean.
            if not broken:
                conn.rollback()
        except psycopg2.Error:
            broken = True
        pool.putconn(conn, close=broken)


def closeall():
    """Close every pooled connection. For shutdown and tests."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
