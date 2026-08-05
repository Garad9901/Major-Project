# Copyright (c) 2026 Yash Garad. All rights reserved.

import decimal

import psycopg2.extras
from psycopg2 import sql


def _json_safe(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def poll_table(conn, table, last_updated_at, seen_ids_at_last_ts):
    """Fetch rows changed since the watermark, classify each as new/updated.

    Watermark is a (last_updated_at, seen_ids_at_last_ts) pair rather than a
    bare timestamp: polling with `updated_at >= watermark` can re-fetch rows
    already processed in a prior cycle if several rows share the exact same
    updated_at as the watermark, so seen_ids_at_last_ts lets us skip those
    without risking `>` silently dropping same-timestamp rows we haven't
    seen yet.
    """
    query = sql.SQL(
        "SELECT * FROM {table} WHERE updated_at >= %s ORDER BY updated_at ASC, id ASC;"
    ).format(table=sql.Identifier(table))

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (last_updated_at,))
        rows = cur.fetchall()

    changes = []
    new_last_updated_at = last_updated_at
    new_seen_ids = set(seen_ids_at_last_ts)

    for row in rows:
        row_id = row["id"]
        row_updated_at = row["updated_at"]

        if row_updated_at == last_updated_at and row_id in seen_ids_at_last_ts:
            continue

        op = "new" if row["created_at"] == row["updated_at"] else "updated"
        changes.append(
            {
                "table": table,
                "op": op,
                "pk": row_id,
                "updated_at": row_updated_at.isoformat(),
                "row": {k: _json_safe(v) for k, v in row.items()},
            }
        )

        if row_updated_at > new_last_updated_at:
            new_last_updated_at = row_updated_at
            new_seen_ids = {row_id}
        elif row_updated_at == new_last_updated_at:
            new_seen_ids.add(row_id)

    return changes, new_last_updated_at, new_seen_ids
