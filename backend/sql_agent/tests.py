# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Regression tests for the SQL guard's table-access control.

These lock in the guarantee that the agent can only ever touch the allowlisted
tables — proven by rejection of a battery of evasion attempts. Pure unit tests:
no database or LLM needed (they call the guard directly).

Run with:  python manage.py test sql_agent
"""

from django.test import SimpleTestCase

from sql_agent import guard
from sql_agent.schema import ALLOWED_TABLES


class OutOfAllowlistRejectionTests(SimpleTestCase):
    # Each case is a query that tries to reach a table OUTSIDE the allowlist
    # (per-student data or system catalogs) through a different SQL construct.
    ATTACKS = {
        "per_student_table": "SELECT * FROM students",
        "schema_qualified": "SELECT * FROM public.students",
        "subquery": "SELECT code FROM courses WHERE credits > (SELECT count(*) FROM students)",
        "cte": "WITH x AS (SELECT * FROM enrollments) SELECT * FROM x",
        "union": "SELECT code FROM courses UNION SELECT roll_number FROM students",
        "join": "SELECT c.code FROM courses c JOIN exam_results e ON true",
        "information_schema": "SELECT table_name FROM information_schema.tables",
        "pg_catalog": "SELECT rolname FROM pg_catalog.pg_roles",
        "auth_table": "SELECT username, password FROM auth_user",
        "fee_payments": "SELECT * FROM fee_payments",
    }

    def test_all_out_of_allowlist_queries_are_rejected(self):
        for name, sql in self.ATTACKS.items():
            with self.subTest(attack=name):
                with self.assertRaises(guard.SqlRejected):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)


class AllowlistedQueriesSucceedTests(SimpleTestCase):
    def test_plain_select_on_allowed_table_passes_and_is_capped(self):
        out = guard.validate_and_cap("SELECT code, title FROM courses", ALLOWED_TABLES)
        self.assertIn("LIMIT 50", out)

    def test_join_across_allowed_tables_passes(self):
        sql = (
            "SELECT c.code, d.name FROM courses c "
            "JOIN departments d ON c.department_id = d.id"
        )
        out = guard.validate_and_cap(sql, ALLOWED_TABLES)
        self.assertIn("LIMIT 50", out)


class WriteAndForbiddenKeywordTests(SimpleTestCase):
    def test_write_statements_rejected(self):
        for sql in (
            "UPDATE courses SET credits = 5",
            "DELETE FROM courses",
            "INSERT INTO courses (code) VALUES ('x')",
            "DROP TABLE courses",
            "SELECT 1; DROP TABLE courses;",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(guard.SqlRejected):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)

    def test_keyword_in_string_literal_is_not_a_false_positive(self):
        # A course literally titled "Update Systems" must not trip the guard.
        out = guard.validate_and_cap(
            "SELECT * FROM courses WHERE title = 'Update Systems'", ALLOWED_TABLES
        )
        self.assertIn("LIMIT 50", out)
