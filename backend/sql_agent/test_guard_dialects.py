# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The SQL guard, exercised under BOTH dialects it must survive.

WHY BOTH, AND WHY THIS FILE EXISTS SEPARATELY FROM tests.py

The guard is the security boundary between a language model's output and the
college's database, and `DIALECT` decides which grammar it validates against.
Porting it to T-SQL is therefore not a formatting change: a case that a Postgres
parser rejects as a syntax error may be perfectly valid T-SQL, and the whole
point of the existing OPENROWSET/OPENQUERY denials was the dialect they become
live in. So every case runs twice, once per dialect, and the reason a case is
rejected has to hold in both.

THE ALLOW CASES ARE NOT FILLER. A guard that rejects legitimate questions gets
relaxed by whoever is on call next, and the relaxation will not be as careful as
the original. Real joins, subqueries, aggregates and ordering must keep working,
and that is asserted here alongside the refusals.

TWO DEFECTS THIS FILE PINS, both found by probing rather than by reading:

  1. FOUR-PART NAMES BYPASSED THE TABLE ALLOWLIST. `t.name` is only the final
     component of an identifier, so

         SELECT * FROM linked_evil.master.dbo.faculty

     reduced to the allowlisted name `faculty` while pointing at a LINKED
     SERVER. Measured as PASSING the allowlist before the fix. Harmless under
     Postgres, where a cross-database name fails at execution; live under T-SQL.
     Identical in shape to ca69849 — an identifier check that inspected only
     part of the identifier.

  2. xp_cmdshell IN A PROJECTION WAS NOT SEEN. As a FROM source it is already
     caught by the allowlist, but

         SELECT xp_cmdshell('whoami') FROM courses

     is a Select over an allowlisted table with the call in the select list,
     where no table check reaches it. The read-only principal DENYs EXECUTE, so
     this was defence in depth — but "the database would have refused it" is
     exactly the reasoning that made the OPENROWSET hole look harmless.
"""

import importlib
import os
import unittest

from django.test import SimpleTestCase

from common.allowlist import ALLOWED_TABLES

DIALECTS = ("postgres", "tsql")

# (label, sql) — {schema} is substituted with the dialect's own default schema.
MUST_REJECT = [
    ("stacked statements", "SELECT 1 FROM courses; DROP TABLE courses"),
    ("GO batch separator", "SELECT * FROM courses\nGO\nDROP TABLE courses"),
    ("WAITFOR DELAY", "SELECT * FROM courses WHERE 1=1 WAITFOR DELAY '00:00:05'"),
    ("xp_cmdshell in projection", "SELECT xp_cmdshell('whoami') FROM courses"),
    ("sp_executesql", "SELECT * FROM courses WHERE id=(SELECT 1) EXEC sp_executesql N'SELECT 1'"),
    ("OPENROWSET", "SELECT * FROM OPENROWSET('SQLNCLI','x','SELECT 1')"),
    ("OPENQUERY", "SELECT * FROM OPENQUERY(linked,'SELECT 1')"),
    ("four-part linked-server name", "SELECT * FROM linked_evil.master.dbo.faculty"),
    ("cross-database name", "SELECT * FROM otherdb.dbo.faculty"),
    ("bare SELECT reaching no table", "SELECT 1"),
    ("system catalog", "SELECT * FROM sys.databases"),
    ("table outside the allowlist", "SELECT * FROM students"),
    ("UPDATE", "UPDATE courses SET title='x'"),
]

MUST_ALLOW = [
    ("count with predicate",
     "SELECT COUNT(*) FROM faculty_development WHERE department = 'Computer Science'"),
    ("join with group by",
     "SELECT d.name, COUNT(*) FROM faculty f JOIN departments d "
     "ON d.id = f.department_id GROUP BY d.name"),
    ("subquery in IN",
     "SELECT * FROM courses WHERE id IN (SELECT course_id FROM course_offerings)"),
    ("aggregate with HAVING",
     "SELECT department, AVG(overall_score) FROM faculty_development "
     "GROUP BY department HAVING COUNT(*) > 10"),
    ("order by with limit", "SELECT title FROM courses ORDER BY title LIMIT 5"),
    ("schema-qualified name", "SELECT * FROM {schema}.courses"),
]

_DEFAULT_SCHEMA = {"postgres": "public", "tsql": "dbo"}


class _GuardUnderDialect:
    """Reimports the guard with SQL_DIALECT set, and restores it afterwards.

    DIALECT is read at import time on purpose — an allowlist that could change
    under a running process is an allowlist with a race in it — so switching it
    for a test means reimporting the module.
    """

    def __init__(self, dialect):
        self.dialect = dialect

    def __enter__(self):
        self._previous = os.environ.get("SQL_DIALECT")
        os.environ["SQL_DIALECT"] = self.dialect
        from sql_agent import guard
        self.guard = importlib.reload(guard)
        assert self.guard.DIALECT == self.dialect
        return self.guard

    def __exit__(self, *exc):
        if self._previous is None:
            os.environ.pop("SQL_DIALECT", None)
        else:
            os.environ["SQL_DIALECT"] = self._previous
        from sql_agent import guard
        importlib.reload(guard)
        return False


class GuardRejectsUnderBothDialectsTests(SimpleTestCase):
    def test_every_injection_case_is_rejected_in_both_dialects(self):
        for dialect in DIALECTS:
            with _GuardUnderDialect(dialect) as guard:
                for label, sql in MUST_REJECT:
                    with self.subTest(dialect=dialect, case=label):
                        with self.assertRaises(guard.SqlRejected):
                            guard.validate_and_cap(sql, ALLOWED_TABLES)


class GuardStillAllowsRealQuestionsTests(SimpleTestCase):
    def test_legitimate_queries_survive_in_both_dialects(self):
        for dialect in DIALECTS:
            with _GuardUnderDialect(dialect) as guard:
                for label, sql in MUST_ALLOW:
                    with self.subTest(dialect=dialect, case=label):
                        out = guard.validate_and_cap(
                            sql.replace("{schema}", _DEFAULT_SCHEMA[dialect]),
                            ALLOWED_TABLES,
                        )
                        self.assertTrue(out.strip())


class LimitRendersAsTopUnderTsqlTests(SimpleTestCase):
    """The row cap must survive the dialect change, in the dialect's own syntax.

    T-SQL has no LIMIT. sqlglot renders the same capped statement as TOP with no
    code change in _cap_limit — verified here rather than assumed, because the
    cap is the only thing bounding how much data one question can return.
    """

    def test_cap_is_expressed_as_TOP(self):
        with _GuardUnderDialect("tsql") as guard:
            out = guard.validate_and_cap("SELECT * FROM courses", ALLOWED_TABLES)
            self.assertIn("TOP", out.upper())
            self.assertNotIn("LIMIT", out.upper())

    def test_a_larger_requested_limit_is_still_capped(self):
        with _GuardUnderDialect("tsql") as guard:
            out = guard.validate_and_cap("SELECT * FROM courses LIMIT 5000", ALLOWED_TABLES)
            self.assertIn(f"TOP {guard.MAX_LIMIT}", out.upper())

    def test_cap_is_expressed_as_LIMIT_under_postgres(self):
        with _GuardUnderDialect("postgres") as guard:
            out = guard.validate_and_cap("SELECT * FROM courses", ALLOWED_TABLES)
            self.assertIn("LIMIT", out.upper())


class UnknownDialectFailsClosedTests(SimpleTestCase):
    def test_an_unrecognised_dialect_refuses_to_load(self):
        # Falling back to a default would parse the model's SQL with whatever
        # sqlglot treats as generic, which accepts a broader grammar than either
        # real backend — a guard validating against a grammar no database
        # speaks.
        previous = os.environ.get("SQL_DIALECT")
        os.environ["SQL_DIALECT"] = "mysql"
        try:
            from sql_agent import guard
            with self.assertRaises(RuntimeError):
                importlib.reload(guard)
        finally:
            if previous is None:
                os.environ.pop("SQL_DIALECT", None)
            else:
                os.environ["SQL_DIALECT"] = previous
            from sql_agent import guard
            importlib.reload(guard)
