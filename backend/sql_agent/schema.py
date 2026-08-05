# Copyright (c) 2026 Yash Garad. All rights reserved.

# Re-exported from the canonical definition so existing callers
# (sql_agent.service, guard) keep working unchanged. Not redefined here — see
# common/allowlist.py.
from common.allowlist import ALLOWED_TABLES, TABLE_NOTES  # noqa: F401

_COLUMNS_SQL = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = ANY(%s)
    ORDER BY table_name, ordinal_position;
"""

_FK_SQL = """
    SELECT
        tc.table_name AS from_table,
        kcu.column_name AS from_column,
        ccu.table_name AS to_table,
        ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
      AND tc.table_name = ANY(%s);
"""


def build_schema_text(conn):
    """Introspects the live DB (as rag_agent_ro) for the whitelisted tables,
    so the prompt always reflects what the agent is actually allowed to
    query — it can never drift from db/sql/create_rag_agent_ro.sql."""
    with conn.cursor() as cur:
        cur.execute(_COLUMNS_SQL, (ALLOWED_TABLES,))
        columns_by_table = {}
        for table_name, column_name, data_type in cur.fetchall():
            columns_by_table.setdefault(table_name, []).append((column_name, data_type))

        cur.execute(_FK_SQL, (ALLOWED_TABLES,))
        foreign_keys = {}
        for from_table, from_column, to_table, to_column in cur.fetchall():
            foreign_keys[(from_table, from_column)] = (to_table, to_column)

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
