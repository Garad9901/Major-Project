# Copyright (c) 2026 Yash Garad. All rights reserved.

import re

import sqlglot
from sqlglot import exp
from sqlglot.tokens import Tokenizer, TokenType

DIALECT = "postgres"
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
