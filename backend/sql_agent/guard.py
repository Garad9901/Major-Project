# Copyright (c) 2026 Yash Garad. All rights reserved.

import os
import re

import sqlglot
from sqlglot import exp
from sqlglot.tokens import Tokenizer, TokenType

from common import schema_map

# The dialect the guard PARSES AND RENDERS in. It must match the database the
# generated SQL will actually run against: parsing T-SQL as Postgres (or the
# reverse) silently changes what the parser accepts, and this parser IS the
# security boundary.
#
# Selectable because both backends stay green during the migration — Postgres
# remains the calibration baseline for every measurement in docs/ until the
# real college schema is in and the port is proven.
#
# Fails closed on an unknown value rather than falling back to a default: an
# unrecognised dialect would otherwise be silently parsed by whatever sqlglot
# treats as generic, which accepts a broader grammar than either real backend.
_SUPPORTED_DIALECTS = ("postgres", "tsql")
DIALECT = (os.getenv("SQL_DIALECT", "").strip().lower() or "postgres")
if DIALECT not in _SUPPORTED_DIALECTS:
    raise RuntimeError(
        f"SQL_DIALECT={DIALECT!r} is not one of {_SUPPORTED_DIALECTS}. "
        "Refusing to start: the guard parses in this dialect, so an unknown "
        "value would validate the model's SQL against a grammar that matches "
        "no database this system talks to."
    )
MAX_LIMIT = 50  # hard cap — not env-configurable on purpose, see README note in service.py

# The literal 5 keywords called out as a hard requirement. Enforced twice:
# structurally below (sqlglot's statement-type check already rules these
# out via the isinstance(stmt, exp.Select) check), and again here as a
# token-level net in case a future parser edge case ever lets one slip
# through. Checking *token type* rather than raw text/regex matters: a
# course literally titled "Update Systems" tokenizes UPDATE as a plain
# STRING, not a TokenType.UPDATE keyword, so it won't false-positive here
# the way a naive `\bUPDATE\b` regex over the raw SQL text would.
_HARD_FORBIDDEN_TOKEN_TYPES = {
    TokenType.INSERT,
    TokenType.UPDATE,
    TokenType.DELETE,
    TokenType.DROP,
    TokenType.ALTER,
}

_CODE_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

# Functions that read data from OUTSIDE the current database. Each one turns a
# permitted SELECT into a reader of remote servers, UNC paths or local files, at
# the privilege of the database process rather than of our read-only principal.
# Named explicitly because they are reads, so no amount of DENY INSERT/UPDATE/
# DELETE on the login excludes them.
#
# T-SQL names are listed even though DIALECT is currently "postgres": the whole
# reason this check exists is the pending migration, and a denylist that only
# covers today's dialect would have to be remembered at exactly the moment
# everything else is changing. dblink/postgres_fdw are the Postgres analogues.
_FORBIDDEN_SOURCE_FUNCTIONS = {
    "OPENROWSET",
    "OPENQUERY",
    "OPENDATASOURCE",
    "OPENXML",
    "DBLINK",
    "DBLINK_EXEC",
}

# Functions that EXECUTE rather than read. Distinct from the set above because
# the reason differs: these do not read a remote source, they run a command.
#
# xp_cmdshell as a FROM source is already caught (it is not an allowlisted
# table), but as a PROJECTION it is not:
#
#     SELECT xp_cmdshell('whoami') FROM courses
#
# parses to a Select over the allowlisted `courses`, with the call in the select
# list where no table check ever sees it. Measured: this passed the allowlist.
#
# The read-only principal DENYs EXECUTE, so this is defence in depth rather than
# the only thing standing in the way — but "the database would have refused it"
# is exactly the reasoning that made the OPENROWSET hole look harmless.
_FORBIDDEN_EXEC_FUNCTIONS = {
    "XP_CMDSHELL",
    "SP_EXECUTESQL",
    "SP_OACREATE",
    "SP_OAMETHOD",
    "XP_DIRTREE",
    "XP_FILEEXIST",
    "XP_REGREAD",
}


# Schema qualifiers the guard will accept on a table reference. Taken from the
# schema map so that "which schema is legitimate" has one source: `public` on
# Postgres, `dbo` on SQL Server, whatever the college actually uses when the
# real map lands. Anything else is treated as a cross-database reference.
#
# The dialect's own default schema is included as well as the map's. Both
# backends stay green during the migration, so the same map is read while
# DIALECT is either "postgres" or "tsql", and `dbo.courses` is an ordinary
# same-database reference on SQL Server exactly as `public.courses` is on
# Postgres. Neither admits `master.dbo.courses`, which carries a CATALOG and is
# refused before the schema is even considered.
_DIALECT_DEFAULT_SCHEMA = {"postgres": "public", "tsql": "dbo"}

_ALLOWED_SCHEMAS = ({
    (spec.get("schema") or "").lower()
    for spec in (schema_map._TABLES.values())
} | {_DIALECT_DEFAULT_SCHEMA[DIALECT]}) - {""}


class SqlRejected(Exception):
    pass


def _strip_code_fences(text):
    return _CODE_FENCE_RE.sub("", text).strip()


def validate_and_cap(raw_model_output, allowed_tables, max_limit=MAX_LIMIT):
    """Turns raw LLM output into a safe-to-run SQL string, or raises
    SqlRejected. Never returns anything but a single capped SELECT."""
    text = _strip_code_fences(raw_model_output).rstrip(";").strip()

    if not text or text.upper() == "NO_QUERY":
        raise SqlRejected("the model reported it could not answer this question with the given schema")

    try:
        statements = [s for s in sqlglot.parse(text, read=DIALECT) if s is not None]
    except Exception as exc:
        raise SqlRejected(f"generated SQL failed to parse: {exc}") from None

    if len(statements) != 1:
        raise SqlRejected(
            f"expected exactly one SQL statement, got {len(statements)} "
            "(stacked/multiple statements are not allowed)"
        )

    stmt = statements[0]

    if not isinstance(stmt, exp.Select):
        raise SqlRejected(f"only SELECT statements are allowed, got {type(stmt).__name__}")

    hit_types = {tok.token_type for tok in Tokenizer().tokenize(text)} & _HARD_FORBIDDEN_TOKEN_TYPES
    if hit_types:
        raise SqlRejected(f"query contains forbidden keyword(s): {', '.join(t.name for t in hit_types)}")

    # EVERY data source must be a NAMED, allowlisted table.
    #
    # This check used to read:
    #
    #     referenced_tables = {t.name.lower() for t in ... if t.name}
    #
    # and the `if t.name` filter is what made it fail OPEN. A data source that
    # is a FUNCTION rather than a named table still parses to an exp.Table, but
    # with an EMPTY name — so the filter discarded it, the set came out empty,
    # and `empty - allowed` is empty, so the query was allowed. "No forbidden
    # table was named" was being treated as "every table named was permitted".
    #
    # Measured against the live guard before the fix:
    #
    #     SELECT 1                                       -> ALLOWED
    #     SELECT * FROM OPENROWSET('SQLNCLI','x','...')  -> ALLOWED
    #     SELECT * FROM OPENQUERY(linked,'SELECT 1')     -> ALLOWED
    #
    # Harmless under DIALECT="postgres", which has no such functions: the query
    # dies at execution. It is NOT harmless under T-SQL, where OPENROWSET and
    # OPENQUERY read remote data sources and files from the perspective of the
    # SQL Server process. A read-only principal does not prevent that, because
    # it is a read. This is fixed here, deliberately BEFORE the dialect switch,
    # so it lands under the dialect we already understand and with the existing
    # suite green behind it.
    table_nodes = list(stmt.find_all(exp.Table))

    unnamed = [t for t in table_nodes if not t.name]
    if unnamed:
        raise SqlRejected(
            "query reads from an unnamed data source (a table-valued function "
            "such as OPENROWSET/OPENQUERY); only named tables are allowed"
        )

    # THE ALLOWLIST MUST SEE THE WHOLE IDENTIFIER, NOT JUST THE LAST PART.
    #
    # `t.name` is only the final component. A T-SQL four-part name
    # server.database.schema.object therefore reduced to an allowlisted table
    # name while pointing somewhere else entirely. Measured before this check:
    #
    #     SELECT * FROM linked_evil.master.dbo.faculty   -> PASSES allowlist
    #                   name='faculty' catalog='linked_evil' db='master'
    #
    # Under T-SQL that reads from a LINKED SERVER, at the privilege of the SQL
    # Server process rather than of our read-only principal — the same escape as
    # OPENROWSET, reached by a different route. It is the identical shape to the
    # bug fixed in ca69849: an identifier check that inspects only part of the
    # identifier.
    #
    # Benign under Postgres, where a cross-database name fails at execution.
    # Live the moment DIALECT becomes "tsql", which is why it is fixed here
    # rather than left to be noticed later.
    #
    # A catalog qualifier is refused outright. A schema qualifier is allowed
    # only when it is one the schema map actually declares, so `dbo.faculty`
    # works on SQL Server and `public.faculty` on Postgres without either
    # opening a door to `master.dbo.faculty`.
    qualified = []
    for t in table_nodes:
        catalog = (t.catalog or "").strip()
        db = (t.db or "").strip()
        if catalog:
            qualified.append(t.sql(dialect=DIALECT))
        elif db and db.lower() not in _ALLOWED_SCHEMAS:
            qualified.append(t.sql(dialect=DIALECT))
    if qualified:
        raise SqlRejected(
            "query names a table outside the current database "
            f"({', '.join(sorted(qualified))}); cross-database and linked-server "
            "references are not allowed"
        )

    referenced_tables = {t.name.lower() for t in table_nodes}

    # A SELECT that reaches no table at all cannot be answering a question about
    # the records, and is the degenerate case of the failure above.
    if not referenced_tables:
        raise SqlRejected("query does not read from any table")

    allowed_lower = {t.lower() for t in allowed_tables}
    disallowed = referenced_tables - allowed_lower
    if disallowed:
        raise SqlRejected(
            f"query references table(s) outside the allowed schema: {', '.join(sorted(disallowed))}"
        )

    # Defence in depth: the same functions can appear as ordinary function calls
    # rather than as a FROM source (in a projection or a WHERE subquery), where
    # they produce no exp.Table node at all and the checks above never see them.
    called = {
        f.sql_name().upper()
        for f in stmt.find_all(exp.Func)
        if hasattr(f, "sql_name")
    }
    for node in stmt.find_all(exp.Anonymous):
        name = node.args.get("this")
        if isinstance(name, str):
            called.add(name.upper())
    remote = called & _FORBIDDEN_SOURCE_FUNCTIONS
    if remote:
        raise SqlRejected(
            f"query calls a remote/external data-source function: {', '.join(sorted(remote))}"
        )

    executing = called & _FORBIDDEN_EXEC_FUNCTIONS
    if executing:
        raise SqlRejected(
            f"query calls a command-execution procedure: {', '.join(sorted(executing))}"
        )

    return _cap_limit(stmt, max_limit).sql(dialect=DIALECT)


def _cap_limit(stmt, max_limit):
    stmt = stmt.copy()
    stmt.set("offset", None)  # pagination isn't supported by this agent

    existing_limit_node = stmt.args.get("limit")
    existing_value = None
    if existing_limit_node is not None:
        try:
            existing_value = int(existing_limit_node.expression.this)
        except (AttributeError, TypeError, ValueError):
            existing_value = None

    final_limit = min(existing_value, max_limit) if existing_value is not None else max_limit
    return stmt.limit(final_limit)
