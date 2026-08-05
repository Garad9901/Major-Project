# Copyright (c) 2026 Yash Garad. All rights reserved.

"""
Seeds 5 sample courses covering distinct topics, runs them through the same
chunk -> embed -> upsert pipeline main.py uses, then fires 5 natural-language
queries at Qdrant and checks the expected course comes back in the top 3
results for each. Exercises the real chunker/embedder/vector_store code —
nothing here is mocked.

Requires the Postgres owner credentials (POSTGRES_*), not rag_agent_ro,
because it needs to INSERT — sync_worker itself only ever reads.

Usage: docker compose exec backend ... no — run inside the sync_worker
container: docker compose exec sync_worker python test_embedding_pipeline.py
"""

import logging
import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from chunker import row_to_text
from embedder import embed_text
from lookups import fetch_department_lookup
from vector_store import search, upsert_point

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [test] %(levelname)s: %(message)s")
logger = logging.getLogger("test_embedding_pipeline")

SUPERUSER_DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "college_rag"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

SAMPLE_COURSES = [
    dict(
        code="TEST-CS501",
        title="Machine Learning Fundamentals",
        credits=4,
        description="Covers supervised and unsupervised learning, neural networks, and model evaluation.",
    ),
    dict(
        code="TEST-CS310",
        title="Database Systems",
        credits=3,
        description="Relational algebra, SQL, normalization, transactions, and indexing.",
    ),
    dict(
        code="TEST-CHEM210",
        title="Organic Chemistry I",
        credits=4,
        description="Structure, nomenclature, and reactions of organic compounds.",
    ),
    dict(
        code="TEST-ENG150",
        title="Shakespearean Literature",
        credits=3,
        description="Close reading of major tragedies and comedies by William Shakespeare.",
    ),
    dict(
        code="TEST-FIN220",
        title="Financial Accounting",
        credits=3,
        description="Principles of recording, summarizing, and reporting financial transactions.",
    ),
]

TEST_QUERIES = [
    ("Which course teaches neural networks and AI models?", "TEST-CS501"),
    ("I want to learn SQL and how databases work.", "TEST-CS310"),
    ("A course about chemical reactions and molecules.", "TEST-CHEM210"),
    ("Looking for a class on Shakespeare's plays.", "TEST-ENG150"),
    ("How do I learn about company financial statements?", "TEST-FIN220"),
]


def seed_sample_courses(conn, department_id):
    rows = []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for course in SAMPLE_COURSES:
            cur.execute(
                """
                INSERT INTO courses (code, title, credits, department_id, description, created_at, updated_at)
                VALUES (%(code)s, %(title)s, %(credits)s, %(department_id)s, %(description)s, now(), now())
                ON CONFLICT (code) DO UPDATE SET
                    title = EXCLUDED.title,
                    credits = EXCLUDED.credits,
                    description = EXCLUDED.description,
                    updated_at = now()
                RETURNING *;
                """,
                {**course, "department_id": department_id},
            )
            rows.append(dict(cur.fetchone()))
    conn.commit()
    return rows


def embed_and_upsert(rows, dept_lookup):
    code_to_id = {}
    for row in rows:
        for key in ("created_at", "updated_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        text = row_to_text("courses", row, dept_lookup)
        vector = embed_text(text)
        upsert_point("courses", row["id"], vector, text, row["updated_at"])
        code_to_id[row["code"]] = row["id"]
        logger.info("embedded %s -> %s", row["code"], text[:90])
    return code_to_id


def run_queries(code_to_id):
    id_to_code = {v: k for k, v in code_to_id.items()}
    passed = 0
    for query, expected_code in TEST_QUERIES:
        vector = embed_text(query)
        results = search(vector, limit=3, table_filter="courses")
        found_codes = [id_to_code.get(r.payload.get("row_id"), f"other:{r.payload.get('row_id')}") for r in results]
        ok = expected_code in found_codes
        passed += int(ok)
        logger.info(
            "query=%r top_matches=%s expected=%s -> %s",
            query, found_codes, expected_code, "PASS" if ok else "FAIL",
        )
    logger.info("%d/%d queries returned the expected course in the top 3 results", passed, len(TEST_QUERIES))
    return passed == len(TEST_QUERIES)


def main():
    conn = psycopg2.connect(**SUPERUSER_DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments ORDER BY id LIMIT 1;")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("No department found in the database — seed at least one department first.")
            department_id = row[0]

        dept_lookup = fetch_department_lookup(conn)
        rows = seed_sample_courses(conn, department_id)
        logger.info("inserted/updated %d sample course rows", len(rows))
    finally:
        conn.close()

    code_to_id = embed_and_upsert(rows, dept_lookup)
    all_passed = run_queries(code_to_id)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
