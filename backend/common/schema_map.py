# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Resolves LOGICAL entity names to the college database's PHYSICAL names.

The migration's central design decision. Every reference to a college table
goes through here, so that adapting to the real college schema is editing
config/schema_map.json and re-running the suite — not auditing 15k lines for
string literals.

WHY A LOADER RATHER THAN A CONSTANT
The map is data, and it is read at import time into module-level constants
because the SQL agent's allowlist is one of its consumers. An allowlist that
could change under a running process is an allowlist with a race in it, so this
resolves once, at startup, and a bad map fails the process rather than degrading
to something permissive.

FAIL CLOSED, LOUDLY
A missing, malformed, or empty map raises. It does NOT fall back to a built-in
default list. That is deliberate and is the lesson of two defects found in this
codebase in the last week — the SQL guard's table allowlist and the identity
cache both treated "nothing found" as "nothing to enforce". A schema map that
silently degraded to an empty allowlist would either break every question or,
worse, be combined with some other default and widen what the model can read.

The one thing this module must never do is return a plausible answer when it
does not know the real one.
"""

import json
import os

_DOC_KEY = "_doc"
_DEFAULT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "schema_map.json")
)

# Overridable so the deployed container can mount the map somewhere else, the
# same way INSTITUTION_CONFIG works. Blank and unset are treated alike: see
# common/env.py for why that distinction has bitten this codebase before.
SCHEMA_MAP_PATH = os.getenv("SCHEMA_MAP", "").strip() or _DEFAULT_PATH


class SchemaMapError(Exception):
    """The map is missing or unusable. Never caught to substitute a default."""


def _load(path=None):
    path = path or SCHEMA_MAP_PATH
    if not os.path.exists(path):
        raise SchemaMapError(
            f"schema map not found at {path}. This file is the only place the "
            "college's table names are recorded; without it the SQL agent has "
            "no allowlist and must not run."
        )
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SchemaMapError(f"{path} is not valid JSON: {exc}") from exc

    tables = raw.get("tables")
    if not isinstance(tables, dict) or not tables:
        raise SchemaMapError(
            f"{path} defines no tables. An empty allowlist is refused rather "
            "than treated as 'allow nothing in particular'."
        )

    default_schema = raw.get("default_schema") or "public"
    resolved = {}
    for logical, spec in tables.items():
        if logical.startswith("_"):
            continue
        if not isinstance(spec, dict):
            raise SchemaMapError(f"{path}: table {logical!r} is not an object")
        physical = spec.get("physical")
        if not physical or not isinstance(physical, str):
            raise SchemaMapError(
                f"{path}: table {logical!r} has no 'physical' name. A logical "
                "name with no physical target cannot be resolved, and guessing "
                "one is how a query reaches the wrong table."
            )
        columns = spec.get("columns") or {}
        if not isinstance(columns, dict):
            raise SchemaMapError(f"{path}: table {logical!r} has a non-object 'columns'")
        resolved[logical] = {
            "physical": physical,
            "schema": spec.get("schema") or default_schema,
            "columns": {k: v for k, v in columns.items() if not k.startswith("_")},
        }
    return resolved, default_schema


_TABLES, DEFAULT_SCHEMA = _load()


def logical_tables():
    """Every logical entity name, in map order (which drives prompt order)."""
    return list(_TABLES)


def physical_tables():
    """The physical names, for the guard allowlist and the grants.

    Bare names, without schema: the guard compares against sqlglot's parsed
    table name, which does not carry the schema qualifier.
    """
    return [spec["physical"] for spec in _TABLES.values()]


def physical(logical_table, qualified=False):
    """The physical name for a logical table. Raises if unknown.

    Raising rather than returning the input unchanged is the point: an
    unrecognised logical name is a bug in the caller, and passing it through
    would produce SQL against a table nobody allowlisted.
    """
    try:
        spec = _TABLES[logical_table]
    except KeyError:
        raise SchemaMapError(
            f"unknown logical table {logical_table!r}; known: {', '.join(_TABLES)}"
        ) from None
    if qualified:
        return f"{spec['schema']}.{spec['physical']}"
    return spec["physical"]


def physical_column(logical_table, logical_column):
    """The physical column name, or the logical one when no override is mapped.

    Unmapped columns pass through unchanged because introspection discovers
    real column names directly from the database; the map only needs entries
    for columns the CODE names literally. This is the one place a pass-through
    is correct, because the table has already been validated against the
    allowlist by the time a column is resolved.
    """
    spec = _TABLES.get(logical_table)
    if spec is None:
        raise SchemaMapError(f"unknown logical table {logical_table!r}")
    return spec["columns"].get(logical_column, logical_column)


def reload_for_tests(path):
    """Re-read the map from `path`. Tests only.

    Named so it cannot be mistaken for a runtime feature: see the note at the
    top about an allowlist that changes under a running process.
    """
    global _TABLES, DEFAULT_SCHEMA
    _TABLES, DEFAULT_SCHEMA = _load(path)
