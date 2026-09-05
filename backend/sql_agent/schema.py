# Copyright (c) 2026 Yash Garad. All rights reserved.

# Re-exported from the canonical definition so existing callers
# (sql_agent.service, guard) keep working unchanged. Not redefined here — see
# common/allowlist.py.
from common import schema_map
from common.allowlist import ALLOWED_TABLES, TABLE_NOTES  # noqa: F401
from sql_agent import guard

# INTROSPECTION, PER DIALECT.
#
# Both forms read INFORMATION_SCHEMA, which is standard, but three things are
# not portable and each one is a silent wrong answer rather than an error:
#
#   * the schema name — 'public' on Postgres, 'dbo' on SQL Server. Taken from
#     the schema map rather than hardcoded, so the real college schema needs no
#     code change.
#   * the placeholder — psycopg2 uses %s, pyodbc uses ?.
#   * the list predicate — Postgres has `= ANY(%s)` and takes a Python list;
#     T-SQL has no array type, so the IN list is expanded to one placeholder per
#     table. The values are still BOUND, never interpolated: these names come
#     from the map rather than from user input, but building SQL by string
#     concatenation in the module that feeds the SQL agent's prompt is a habit
#     worth not having.
#
# The RENDERING below is shared and iterates ALLOWED_TABLES, so prompt order
# follows map order on both backends — which is what the ordering assertion in
# common/test_schema_map.py protects.

_PG_COLUMNS_SQL = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = ANY(%s)
    ORDER BY table_name, ordinal_position;
"""

# FOREIGN KEYS FROM pg_catalog, NOT information_schema.
#
# This query used to read information_schema.constraint_column_usage, which is
# PRIVILEGE-FILTERED: Postgres shows a row there only for constraints on tables
# the current user OWNS. The SQL agent always connects as rag_agent_ro, which
# owns nothing, so it saw NOTHING. Measured:
#
#     as rag_agent_ro: 0 FK rows visible
#     as owner:       30 FK rows visible
#
# The prompt has therefore never contained the REFERENCES hints this function
# was written to emit, on any deployment, since the agent has always connected
# as the read-only role. The docstring's claim that the prompt "always reflects
# what the agent is actually allowed to query" was true of columns and silently
# false of relationships.
#
# It fails in the quiet direction — the model is left to infer join keys from
# column names — which is why nothing surfaced it. It is a plausible
# contributor to the wrong-table join defect corrected earlier.
#
# pg_catalog is not privilege-filtered, so a read-only role sees the real
# constraints. The unnest-with-ordinality pairing handles composite keys, where
# conkey and confkey are position-matched arrays.
_PG_FK_SQL = """
    SELECT
        src.relname  AS from_table,
        srcatt.attname AS from_column,
        tgt.relname  AS to_table,
        tgtatt.attname AS to_column
    FROM pg_constraint c
    JOIN pg_class src ON src.oid = c.conrelid
    JOIN pg_class tgt ON tgt.oid = c.confrelid
    JOIN pg_namespace n ON n.oid = src.relnamespace
    JOIN LATERAL unnest(c.conkey)  WITH ORDINALITY AS sk(attnum, ord) ON TRUE
    JOIN LATERAL unnest(c.confkey) WITH ORDINALITY AS tk(attnum, ord) ON tk.ord = sk.ord
    JOIN pg_attribute srcatt ON srcatt.attrelid = c.conrelid  AND srcatt.attnum = sk.attnum
    JOIN pg_attribute tgtatt ON tgtatt.attrelid = c.confrelid AND tgtatt.attnum = tk.attnum
    WHERE c.contype = 'f' AND n.nspname = %s AND src.relname = ANY(%s);
"""

_TSQL_COLUMNS_SQL = """
    SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({placeholders})
    ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

_TSQL_FK_SQL = """
    SELECT
        fk_tab.name AS from_table,
        fk_col.name AS from_column,
        pk_tab.name AS to_table,
        pk_col.name AS to_column
    FROM sys.foreign_keys fk
    JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
    JOIN sys.tables  fk_tab ON fk_tab.object_id = fkc.parent_object_id
    JOIN sys.columns fk_col ON fk_col.object_id = fkc.parent_object_id
                           AND fk_col.column_id = fkc.parent_column_id
    JOIN sys.tables  pk_tab ON pk_tab.object_id = fkc.referenced_object_id
    JOIN sys.columns pk_col ON pk_col.object_id = fkc.referenced_object_id
                           AND pk_col.column_id = fkc.referenced_column_id
    WHERE SCHEMA_NAME(fk_tab.schema_id) = ?
      AND fk_tab.name IN ({placeholders});
"""


def _introspection_queries():
    """(columns_sql, fk_sql, params) for the active dialect."""
    schema_name = schema_map.DEFAULT_SCHEMA
    if guard.DIALECT == "tsql":
        schema_name = "dbo" if schema_name == "public" else schema_name
        placeholders = ", ".join("?" for _ in ALLOWED_TABLES)
        return (
            _TSQL_COLUMNS_SQL.format(placeholders=placeholders),
            _TSQL_FK_SQL.format(placeholders=placeholders),
            [schema_name, *ALLOWED_TABLES],
        )
    return _PG_COLUMNS_SQL, _PG_FK_SQL, (schema_name, list(ALLOWED_TABLES))


def build_schema_text(conn):
    """Introspects the live DB (as rag_agent_ro) for the whitelisted tables,
    so the prompt always reflects what the agent is actually allowed to
    query — it can never drift from db/sql/create_rag_agent_ro.sql."""
    columns_sql, fk_sql, params = _introspection_queries()
    # pyodbc cursors are not context managers in the way psycopg2's are, so the
    # cursor is closed explicitly rather than with `with`.
    cur = conn.cursor()
    try:
        cur.execute(columns_sql, params)
        columns_by_table = {}
        for table_name, column_name, data_type in cur.fetchall():
            columns_by_table.setdefault(table_name, []).append((column_name, data_type))

        cur.execute(fk_sql, params)
        foreign_keys = {}
        for from_table, from_column, to_table, to_column in cur.fetchall():
            foreign_keys[(from_table, from_column)] = (to_table, to_column)
    finally:
        cur.close()

    lines = []
    for table in ALLOWED_TABLES:
        if table not in columns_by_table:
            continue
        # A one-line statement of what the table holds, above its columns.
        # Column names alone are not enough to tell `faculty` (staff directory)
        # apart from `faculty_development` (the survey) — see TABLE_NOTES.
        note = TABLE_NOTES.get(table)
        if note:
            lines.append(f"-- {note}")
        lines.append(f"TABLE {table} (")
        for column_name, data_type in columns_by_table[table]:
            fk = foreign_keys.get((table, column_name))
            suffix = f" REFERENCES {fk[0]}({fk[1]})" if fk else ""
            lines.append(f"  {column_name} {data_type}{suffix},")
        lines.append(")")
        lines.append("")

    return "\n".join(lines)
