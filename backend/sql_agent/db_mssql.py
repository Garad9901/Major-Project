# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The college's SQL Server, read-only, pooled. The T-SQL sibling of db.py.

A SEPARATE MODULE rather than branches threaded through db.py. The Postgres path
is the calibration baseline for every measurement in docs/ and stays the only
tested path until the port is proven, so it is left byte-for-byte alone; db.py
dispatches to this module when SQL_DIALECT=tsql. When the migration completes
and Postgres is no longer the college store, this replaces it rather than
merging into it.

WHY THE POOL EXISTS HERE — and how the reason differs from Postgres

db.py's pool is NOT about latency. Profiling put connecting at 0.01s against a
~28s answer. It exists because rag_agent_ro has CONNECTION LIMIT 10 and one
question opened TWO connections (schema introspection, then the query), so past
about five simultaneous questions Postgres refused outright.

SQL Server has no per-login connection limit by default, so that specific
ceiling does not transfer. The pool is kept anyway for the other half of the
reason: it BOUNDS how many connections one busy moment can open against a server
this system does not own. On the college's production database, "the assistant
opened ninety connections" is their incident, not ours, and we would have caused
it. A bound we chose is better than a limit they discover.

pyodbc does its own driver-manager pooling, which is not the same thing: it
reuses connections but does not cap how many exist. The explicit bound is the
point.
"""

import contextlib
import logging
import os
import queue
import threading

from common import env
from common.exceptions import DatabaseUnavailable

logger = logging.getLogger("sql_agent")

# The ODBC driver NAME, configurable.
#
# Hardcoding "ODBC Driver 18 for SQL Server" fails on a machine carrying 17, or
# a later release, with an ODBC error that reads like a network problem
# ("data source name not found"). Since the college's machine is not ours to
# inspect in advance, the name is configuration, and a failure to find it lists
# what IS installed — turning a confusing outage into a one-line diagnosis.
ODBC_DRIVER = env.env_or("MSSQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")

MSSQL_CONFIG = {
    "host": env.env_chain("MSSQL_HOST", default="mssql"),
    "port": env.env_chain("MSSQL_PORT", default="1433"),
    "database": env.env_chain("MSSQL_DB", default="college_records"),
    "user": env.env_or("MSSQL_RO_USER", "rag_agent_ro"),
    "password": os.getenv("MSSQL_RO_PASSWORD"),
}

CONNECT_TIMEOUT_S = int(env.env_or("MSSQL_CONNECT_TIMEOUT", "5"))
POOL_MAX = int(env.env_or("MSSQL_POOL_MAX", "8"))

# TLS. READ THIS BEFORE CHANGING IT.
#
# ODBC Driver 18 defaults to Encrypt=yes AND validates the server certificate.
# A development SQL Server has a self-signed certificate, so the connection
# fails, and every search result offers the same fix:
#
#     TrustServerCertificate=yes
#
# That works locally and is a genuine vulnerability in production: it disables
# certificate validation on the connection carrying every student record across
# the college network, so anything in path can present any certificate and read
# or alter the traffic. Nothing complains, because from the application's point
# of view it is working.
#
# It is the same shape as the HSTS defect found in this project: a setting whose
# local convenience is indistinguishable from its production weakness.
#
# So it is allowed ONLY outside production, and config/secret_guards.py refuses
# to boot production with it set — the same mechanism that refuses default
# passwords, for the same reason: a credential-grade misconfiguration should
# stop the process, not produce a log line nobody reads.
#
# The real deployment answer is to trust the college server's certificate
# properly. That is a Phase 7 runbook item and the DBA has to supply it.
TRUST_SERVER_CERTIFICATE = env.env_or("MSSQL_TRUST_SERVER_CERTIFICATE", "no").lower() in (
    "1", "yes", "true", "on",
)

_pool = None
_pool_lock = threading.Lock()


class _BoundedPool:
    """A fixed-ceiling pool of pyodbc connections.

    Deliberately simple: a queue of idle connections plus a semaphore capping
    how many exist at once. Borrowing past the cap raises rather than blocking
    forever, because the orchestrator already has a queue with a timeout in
    front of it and a second unbounded wait there would hide exhaustion instead
    of reporting it.
    """

    def __init__(self, maxsize, factory):
        self._idle = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(maxsize)
        self._factory = factory

    def borrow(self):
        if not self._slots.acquire(blocking=False):
            raise DatabaseUnavailable(
                f"no free database connection (pool of {POOL_MAX} exhausted)"
            )
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            pass
        try:
            return self._factory()
        except Exception:
            self._slots.release()
            raise

    def give_back(self, conn, close=False):
        if close:
            try:
                conn.close()
            except Exception:
                pass
        else:
            self._idle.put(conn)
        self._slots.release()

    def closeall(self):
        while True:
            try:
                self._idle.get_nowait().close()
            except queue.Empty:
                break
            except Exception:
                pass


def _connection_string():
    cfg = MSSQL_CONFIG
    parts = [
        f"DRIVER={{{ODBC_DRIVER}}}",
        f"SERVER={cfg['host']},{cfg['port']}",
        f"DATABASE={cfg['database']}",
        f"UID={cfg['user']}",
        f"PWD={cfg['password'] or ''}",
        "Encrypt=yes",
        f"Connection Timeout={CONNECT_TIMEOUT_S}",
        # The connection is read-only by intent AND by grant. This hints it to
        # the server as well, which lets SQL Server route it to a readable
        # secondary if the college runs an availability group — their
        # architecture, not ours, but free to support and rude not to.
        "ApplicationIntent=ReadOnly",
        "APP=CollegeAssistant",
    ]
    if TRUST_SERVER_CERTIFICATE:
        parts.append("TrustServerCertificate=yes")
    return ";".join(parts) + ";"


def _connect():
    import pyodbc

    try:
        return pyodbc.connect(_connection_string(), timeout=CONNECT_TIMEOUT_S)
    except pyodbc.Error as exc:
        # A MISSING DRIVER MUST NOT LOOK LIKE A NETWORK FAULT.
        #
        # A first version caught pyodbc.InterfaceError for this. Measured: a
        # wrong driver name actually raises plain pyodbc.Error with SQLSTATE
        # '01000' and the text "Can't open lib ... file not found", so the
        # specific handler never ran and the operator got a bare connection
        # error naming a driver they would then go looking for on the network.
        #
        # Detected by SQLSTATE and message rather than exception class, because
        # the class was the thing that turned out to be wrong.
        sqlstate = (exc.args[0] if exc.args else "") or ""
        message = str(exc)
        driver_problem = sqlstate in ("IM002", "IM003", "01000") or any(
            marker in message
            for marker in ("Can't open lib", "file not found", "Data source name not found")
        )
        if driver_problem:
            installed = ", ".join(pyodbc.drivers()) or "none"
            raise DatabaseUnavailable(
                f"could not load ODBC driver {ODBC_DRIVER!r}: {exc}. "
                f"Drivers installed on this machine: {installed}. "
                "Set MSSQL_ODBC_DRIVER to one of those names."
            ) from exc
        raise DatabaseUnavailable(f"could not connect to the college database: {exc}") from exc


def _get_pool():
    """Create the pool on first use, not at import.

    Same reasoning as db.py: the backend can start before the database is
    reachable, and an import-time failure would stop the module loading at all
    rather than producing a clean DatabaseUnavailable later.
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            _pool = _BoundedPool(POOL_MAX, _connect)
            logger.info(
                "college SQL Server pool ready (max=%d, driver=%r, trust_cert=%s)",
                POOL_MAX, ODBC_DRIVER, TRUST_SERVER_CERTIFICATE,
            )
    return _pool


@contextlib.contextmanager
def connection():
    """Borrow a pooled read-only connection; always give it back.

    A connection that raised is closed rather than returned, so a broken socket
    is not handed to the next caller — one network blip would otherwise poison a
    pool slot for the life of the process.
    """
    import pyodbc

    pool = _get_pool()
    conn = pool.borrow()
    broken = False
    try:
        yield conn
    except pyodbc.Error:
        broken = True
        raise
    finally:
        try:
            if not broken:
                # The login is denied every write, but pyodbc still opens a
                # transaction — roll back so the next borrower starts clean.
                conn.rollback()
        except pyodbc.Error:
            broken = True
        pool.give_back(conn, close=broken)


def closeall():
    """Close every pooled connection. For shutdown and tests."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None
