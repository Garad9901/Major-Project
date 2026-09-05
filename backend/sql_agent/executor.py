# Copyright (c) 2026 Yash Garad. All rights reserved.

import psycopg2
import psycopg2.extras

from common.exceptions import DatabaseUnavailable

from . import db, guard
from . import db_mssql

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
    if guard.DIALECT == "tsql":
        return _run_query_tsql(sql)

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


def _run_query_tsql(sql):
    """The T-SQL sibling of run_query. Same contract, different enforcement.

    THE TIMEOUT IS NOT THE SAME MECHANISM AND CANNOT BE.

    Postgres takes `SET LOCAL statement_timeout`, scoped to the transaction so
    it cannot leak to the next borrower of a pooled connection. T-SQL has no
    per-statement server-side equivalent that a read-only login may set:
    SET LOCK_TIMEOUT bounds only lock waits, not execution, and the real
    equivalent (a Resource Governor pool) is server configuration the college
    owns, not something this application may impose.

    So the bound is applied CLIENT-side, via pyodbc's cursor timeout, and the
    difference is worth stating plainly rather than papering over: a client-side
    timeout stops us WAITING, it does not stop the SERVER working. A runaway
    query keeps consuming the college's CPU after we have given up on it.

    That is a weaker guarantee than the Postgres path has. It is mitigated by
    the row cap in guard.py and by the read-only login, and the honest fix is a
    Resource Governor limit their DBA sets — a Phase 7 runbook item.

    QUERY_TIMEOUT is set on the CONNECTION rather than the cursor because
    pyodbc applies it there; it is reset in the finally so a pooled connection
    is handed on clean, which is the same property `SET LOCAL` gives for free.
    """
    import pyodbc

    try:
        with db_mssql.connection() as conn:
            previous = conn.timeout
            conn.timeout = max(1, STATEMENT_TIMEOUT_MS // 1000)
            cur = conn.cursor()
            try:
                cur.execute(sql)
                # T-SQL LEAVES AGGREGATE COLUMNS UNNAMED, POSTGRES DOES NOT.
                #
                # `SELECT COUNT(*) FROM t` yields a column named "count" on
                # Postgres and a column named "" on SQL Server. Measured on the
                # same question through the same pipeline:
                #
                #     postgres -> [{'count': 1916}]
                #     tsql     -> [{'': 1916}]
                #
                # The number is right either way, but an EMPTY KEY is not a
                # harmless cosmetic difference: these rows are handed to
                # synthesis as evidence and to verification_agent's fast scalar
                # check, both of which read them by key. A blank key is the kind
                # of thing that reads as "no data" somewhere downstream.
                #
                # Named positionally rather than guessed at semantically —
                # inventing "count" here would be asserting what the aggregate
                # MEANS, which is the model's job and not the driver's.
                columns = (
                    [d[0] or f"column_{i + 1}" for i, d in enumerate(cur.description)]
                    if cur.description else []
                )
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
                return columns, rows
            finally:
                cur.close()
                conn.timeout = previous
    except pyodbc.OperationalError as exc:
        raise DatabaseUnavailable(f"database connection lost mid-query: {exc}") from exc
