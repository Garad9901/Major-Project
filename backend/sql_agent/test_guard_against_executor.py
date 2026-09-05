# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The guard's verdicts, checked against a REAL DATABASE rather than the parser.

WHY THIS IS A DIFFERENT TEST FROM test_guard_dialects.py

That file asserts what the guard DECIDES. This one asserts what happens next:

  * a denied statement must be denied by the GUARD, so it never reaches the
    database at all. "The server would have refused it anyway" is a weaker
    guarantee than "it was never sent", and it is the reasoning that made the
    OPENROWSET hole look harmless for as long as it did.
  * an allowed statement must actually RUN and return rows. A guard that lets a
    query through into a driver that then cannot decode the result is not a
    working path, and nothing at the SQL level would notice.

The second half is not padding. It is how the DATETIMEOFFSET defect was found:
every allow-case was valid SQL, the guard passed it, SQL Server executed it, and
pyodbc raised "ODBC SQL type -155 is not yet supported" decoding the rows. Any
question returning a created_at column failed on the T-SQL path while the
identical Postgres query worked.

Skipped unless a college database is reachable, because it needs one. Run with:

    SQL_DIALECT=tsql MSSQL_RO_PASSWORD=... \\
      python manage.py test sql_agent.test_guard_against_executor
"""

import unittest

from django.test import SimpleTestCase

from common.allowlist import ALLOWED_TABLES
from common.exceptions import DatabaseUnavailable
from sql_agent import db, db_mssql, executor, guard

MUST_NEVER_REACH_THE_DATABASE = [
    ("stacked statements", "SELECT 1 FROM courses; DROP TABLE courses"),
    ("GO batch separator", "SELECT * FROM courses\nGO\nDROP TABLE courses"),
    ("WAITFOR DELAY", "SELECT * FROM courses WHERE 1=1 WAITFOR DELAY '00:00:05'"),
    ("xp_cmdshell in a projection", "SELECT xp_cmdshell('whoami') FROM courses"),
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

MUST_RUN_AND_RETURN_ROWS = [
    ("count with predicate",
     "SELECT COUNT(*) FROM faculty_development WHERE department = 'Computer Science'"),
    ("join with group by",
     "SELECT d.name, COUNT(*) FROM faculty f JOIN departments d "
     "ON d.id = f.department_id GROUP BY d.name"),
    # SELECT * deliberately: it pulls created_at/updated_at, which is what
    # exposed the DATETIMEOFFSET decode failure. Narrowing the projection here
    # would quietly stop testing the thing this case exists to test.
    ("subquery selecting whole rows",
     "SELECT * FROM courses WHERE id IN (SELECT course_id FROM course_offerings)"),
    ("aggregate with HAVING",
     "SELECT department, AVG(data_literacy_score) FROM faculty_development "
     "GROUP BY department HAVING COUNT(*) > 10"),
    ("order by with a row cap", "SELECT title FROM courses ORDER BY title LIMIT 5"),
]


def _college_db():
    return db_mssql if guard.DIALECT == "tsql" else db


def _database_reachable():
    try:
        with _college_db().connection():
            return True
    except Exception:
        return False


@unittest.skipUnless(_database_reachable(), "no college database reachable")
class GuardVerdictsAgainstARealDatabaseTests(SimpleTestCase):
    databases = set()

    def test_denied_statements_never_reach_the_database(self):
        for label, sql in MUST_NEVER_REACH_THE_DATABASE:
            with self.subTest(dialect=guard.DIALECT, case=label):
                with self.assertRaises(
                    guard.SqlRejected,
                    msg=f"{label!r} was NOT stopped by the guard; it would have been "
                        f"sent to the database and we would be relying on the server "
                        f"to refuse it",
                ):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)

    def test_allowed_statements_actually_execute(self):
        for label, sql in MUST_RUN_AND_RETURN_ROWS:
            with self.subTest(dialect=guard.DIALECT, case=label):
                capped = guard.validate_and_cap(sql, ALLOWED_TABLES)
                try:
                    columns, rows = executor.run_query(capped)
                except DatabaseUnavailable:
                    raise
                self.assertTrue(rows, f"{label!r} returned no rows")
                # Every column must be NAMED. T-SQL leaves aggregates unnamed and
                # a blank key reads as "no data" to synthesis and to the fast
                # scalar check, both of which read these rows by key.
                for key in rows[0]:
                    self.assertTrue(str(key).strip(), f"{label!r} produced a blank column key")

    def test_timestamp_columns_decode(self):
        """The DATETIMEOFFSET regression, pinned on its own.

        pyodbc has no built-in converter for SQL type -155, so before the
        converter was registered every row carrying a `timestamp with time zone`
        raised while the identical Postgres query succeeded.
        """
        capped = guard.validate_and_cap("SELECT * FROM departments", ALLOWED_TABLES)
        columns, rows = executor.run_query(capped)
        self.assertTrue(rows)
        self.assertIn("created_at", columns)
