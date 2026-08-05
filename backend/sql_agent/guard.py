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

    referenced_tables = {t.name.lower() for t in stmt.find_all(exp.Table) if t.name}
    allowed_lower = {t.lower() for t in allowed_tables}
    disallowed = referenced_tables - allowed_lower
    if disallowed:
        raise SqlRejected(
            f"query references table(s) outside the allowed schema: {', '.join(sorted(disallowed))}"
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
