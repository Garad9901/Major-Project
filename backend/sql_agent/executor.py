# Copyright (c) 2026 Yash Garad. All rights reserved.

import psycopg2
import psycopg2.extras

from common.exceptions import DatabaseUnavailable

from . import db

# Extra defense-in-depth beyond the role-level grants and
# default_transaction_read_only: even a legitimate SELECT shouldn't be
# allowed to hang the connection indefinitely.
STATEMENT_TIMEOUT_MS = 5000

# Bound how long we wait to establish a connection so a DOWN database fails
# fast instead of hanging the request.
CONNECT_TIMEOUT_S = 5


def run_query(sql):
    """Runs an already-validated, already-capped SELECT as rag_agent_ro.
    Never call this with unvalidated SQL — guard.validate_and_cap() is what
    makes this safe to call at all.

    Raises DatabaseUnavailable if the database is unreachable or the
    connection drops mid-query. That exception carries a user-safe message;
    the raw psycopg2 error stays in the logs.
    """
    # Pooled connection — see the ceiling note in sql_agent/db.py. This used to
    # open a second fresh connection per question on top of the one schema
    # introspection already opened.
    try:
        with db.connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Set per-statement, not via autocommit on a shared connection:
                # the pool hands this connection to the next caller, so the
                # timeout must not leak beyond this query.
                cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS};")
                cur.execute(sql)
                rows = [dict(row) for row in cur.fetchall()]
                columns = [desc[0] for desc in cur.description] if cur.description else []
            return columns, rows
    except psycopg2.OperationalError as exc:
        # Connection dropped mid-query (server restarted, network blip, etc.).
        # db.connection() has already discarded the broken socket.
        raise DatabaseUnavailable(f"database connection lost mid-query: {exc}") from exc
