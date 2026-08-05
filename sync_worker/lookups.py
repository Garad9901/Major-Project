# Copyright (c) 2026 Yash Garad. All rights reserved.

def fetch_department_lookup(conn):
    """id -> name for every department, used to resolve FKs when chunking
    faculty/program/course rows into readable text (see chunker.py)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM departments;")
        return {row[0]: row[1] for row in cur.fetchall()}
