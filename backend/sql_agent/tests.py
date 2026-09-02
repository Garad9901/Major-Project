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
from common.allowlist import TABLE_NOTES


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


class WrongTableForFacultyCountsTests(SimpleTestCase):
    """Audit log entry 801: a wrong count reached a user.

    Asked "How many faculty are in the Computer Science department?" in
    production, the SQL agent generated

        SELECT COUNT(*) FROM faculty WHERE department_id = (
            SELECT id FROM departments WHERE name = 'Computer Science')

    which replays to 2. The survey holds 1,916. `faculty` is an 11-row staff
    directory; `faculty_development` is the 13,000-row survey.

    BOTH table notes were already reaching the prompt — that was checked before
    anything was changed. The defect was that the `faculty` note's redirect list
    ("scores, competency levels, experience or development needs") omitted
    counting, which is the most common question anyone asks about faculty. A
    model reading it could reasonably conclude counting was not redirected.

    These assert the GUIDANCE, not the model. What the model does with correct
    guidance is measured by the experiment harness, not pinned by a unit test.
    """

    def test_the_faculty_note_redirects_counting(self):
        """A REDIRECT, not a prohibition, and the difference is measured.

        A first attempt led with "DO NOT use this table to COUNT faculty". It
        stopped the wrong answer and produced NO_QUERY instead — the model took
        the prohibition and concluded the question was unanswerable rather than
        switching tables. So this asserts the note says where to GO.
        """
        note = TABLE_NOTES["faculty"]
        lowered = note.lower()
        self.assertIn("how many", lowered)
        self.assertIn("faculty_development", note)
        # The redirect must appear in the same breath as the count language,
        # not merely somewhere in the note.
        how_many_at = lowered.index("how many")
        self.assertIn("faculty_development", note[how_many_at:])

    def test_the_faculty_note_names_the_replacement(self):
        self.assertIn("faculty_development", TABLE_NOTES["faculty"])

    def test_the_faculty_note_says_the_row_count_is_tiny(self):
        """The model needs to know 11 rows cannot be a college's faculty."""
        self.assertIn("handful of rows", TABLE_NOTES["faculty"].lower())

    def test_the_survey_note_claims_counts(self):
        """The other half of the pair: faculty_development must positively
        claim counting, not merely be available for it."""
        note = TABLE_NOTES["faculty_development"].lower()
        self.assertIn("faculty numbers", note)
        self.assertIn("counts by department", note)

    def test_both_notes_reach_the_generated_schema_text(self):
        """The prompt is what matters, not the dict.

        Uses the LIVE read-only connection rather than a fake, because the thing
        being pinned is that build_schema_text actually emits the notes — and a
        fake connection returning no columns would emit no tables and pass
        vacuously. Skips when no database is reachable, so the suite still runs
        offline.
        """
        from sql_agent import db, schema
        try:
            with db.connection() as conn:
                text = schema.build_schema_text(conn)
        except Exception as exc:                     # noqa: BLE001 - any DB error
            self.skipTest(f"no database available: {type(exc).__name__}")
        self.assertIn("use faculty_development", text)
        self.assertIn("counts by department", text)
        # Guards the guard: an empty schema would satisfy neither assertion
        # above only by accident, so assert it is non-trivial too.
        self.assertGreater(len(text), 1000, "schema text looks empty")

    def test_the_sql_prompt_carries_the_worked_examples(self):
        """The examples are what actually fixed this, so they are pinned.

        Prohibition swung the model to NO_QUERY; a demonstration is what a 7B
        model follows. If a future edit trims the prompt, this fails rather
        than quietly restoring the wrong-table answer.
        """
        from sql_agent.llm_client import SYSTEM_PROMPT_TEMPLATE
        self.assertIn(
            "SELECT COUNT(*) FROM faculty_development WHERE department = "
            "'Computer Science'",
            SYSTEM_PROMPT_TEMPLATE,
        )
        self.assertIn("SELECT email FROM faculty WHERE last_name", SYSTEM_PROMPT_TEMPLATE)


class UnnamedDataSourceRejectionTests(SimpleTestCase):
    """The allowlist used to FAIL OPEN on data sources that are not named tables.

    A function used as a data source still parses to an exp.Table, but with an
    EMPTY name. The old check filtered those out with `if t.name`, so the set of
    referenced tables came out empty, and `empty_set - allowed` is empty — which
    read as "nothing disallowed" and let the query through.

    Measured against the guard before the fix:

        SELECT 1                                       -> ALLOWED
        SELECT * FROM OPENROWSET('SQLNCLI','x','...')  -> ALLOWED
        SELECT * FROM OPENQUERY(linked,'SELECT 1')     -> ALLOWED

    Inert under DIALECT="postgres" (no such functions — the query fails at
    execution) and live under T-SQL, where these read remote servers, UNC paths
    and local files AS THE DATABASE PROCESS. Being reads, they are not excluded
    by the read-only principal or by DENY INSERT/UPDATE/DELETE.

    These tests exist to fail loudly if the dialect switch reintroduces it.
    """

    UNNAMED_SOURCES = [
        "SELECT * FROM OPENROWSET('SQLNCLI', 'Server=x;', 'SELECT 1')",
        "SELECT * FROM OPENQUERY(linked_server, 'SELECT 1')",
        "SELECT * FROM OPENDATASOURCE('SQLNCLI', 'Server=x;').db.dbo.t",
    ]

    def test_unnamed_data_sources_are_rejected(self):
        for sql in self.UNNAMED_SOURCES:
            with self.subTest(sql=sql):
                with self.assertRaises(guard.SqlRejected):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)

    def test_select_touching_no_table_is_rejected(self):
        # The degenerate form of the same failure: a SELECT that reaches no
        # table cannot be answering a question about the records.
        with self.assertRaises(guard.SqlRejected):
            guard.validate_and_cap("SELECT 1", ALLOWED_TABLES)

    def test_remote_source_function_names_are_denied(self):
        # Defence in depth: the same functions called somewhere OTHER than the
        # FROM clause produce no exp.Table node, so the table checks never see
        # them.
        for fn in ("OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "DBLINK"):
            with self.subTest(fn=fn):
                self.assertIn(fn, guard._FORBIDDEN_SOURCE_FUNCTIONS)

    def test_legitimate_queries_still_pass(self):
        # The fix must not narrow what the agent can legitimately do. A guard
        # that rejects real questions gets relaxed by whoever is on call next.
        table = sorted(ALLOWED_TABLES)[0]
        out = guard.validate_and_cap(f"SELECT * FROM {table}", ALLOWED_TABLES)
        self.assertIn(table, out.lower())
