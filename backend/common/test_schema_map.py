# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The schema adapter must change nothing today and fail closed when broken.

Two properties, and the first matters more than it looks:

  1. THE DERIVED ALLOWLIST IS IDENTICAL TO THE ONE IT REPLACES. The adapter's
     job is to make the real college schema cheap to adopt later. Its job today
     is to be invisible. If deriving the allowlist from the map widened or
     narrowed it by even one table, that would be a silent change to what the
     language model can read — the exact class of defect fixed in ca69849.

  2. A MISSING OR MALFORMED MAP RAISES. It does not fall back to a default list.
     Two defects found in this codebase in the same week (the SQL guard's table
     allowlist and the identity cache) both treated "nothing found" as "nothing
     to enforce". A schema map that degraded quietly would be the third.

Run with:  python manage.py test common.test_schema_map
"""

import json
import os
import tempfile

from django.test import SimpleTestCase

from common import schema_map
from common.allowlist import ALLOWED_TABLES


class DerivedAllowlistIsUnchangedTests(SimpleTestCase):
    def test_physical_tables_match_the_previous_hardcoded_list_exactly(self):
        # Order included: schema.py renders the prompt in this order, so a
        # reordering would change the prompt and invalidate the prefix cache
        # measurements in docs/LATENCY.md even though the set is the same.
        self.assertEqual(schema_map.physical_tables(), list(ALLOWED_TABLES))

    def test_every_allowlisted_table_resolves(self):
        for name in ALLOWED_TABLES:
            with self.subTest(table=name):
                self.assertEqual(schema_map.physical(name), name)

    def test_excluded_tables_are_not_reachable(self):
        # The personal-data tables are deliberately absent. If one ever appears
        # in the map, the SQL agent can read it the same day.
        for name in ("students", "enrollments", "attendance", "exam_results", "fee_payments"):
            with self.subTest(table=name):
                self.assertNotIn(name, schema_map.logical_tables())
                with self.assertRaises(schema_map.SchemaMapError):
                    schema_map.physical(name)


class SchemaMapFailsClosedTests(SimpleTestCase):
    def _write(self, payload):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, fh)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_missing_file_raises(self):
        with self.assertRaises(schema_map.SchemaMapError):
            schema_map._load("/nonexistent/schema_map.json")

    def test_empty_table_set_raises_rather_than_allowing_nothing_quietly(self):
        path = self._write({"tables": {}})
        with self.assertRaises(schema_map.SchemaMapError):
            schema_map._load(path)

    def test_table_without_a_physical_name_raises(self):
        # Guessing that logical == physical here is how a query reaches a table
        # nobody allowlisted on a schema where the names differ.
        path = self._write({"tables": {"faculty": {"columns": {}}}})
        with self.assertRaises(schema_map.SchemaMapError):
            schema_map._load(path)

    def test_malformed_json_raises(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        fh.write("{not json")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        with self.assertRaises(schema_map.SchemaMapError):
            schema_map._load(fh.name)

    def test_unknown_logical_name_raises_rather_than_passing_through(self):
        with self.assertRaises(schema_map.SchemaMapError):
            schema_map.physical("HR_Staff_typo")


class RemappingWorksTests(SimpleTestCase):
    """The point of the whole exercise: renaming is a one-file edit."""

    def test_a_remapped_table_resolves_to_the_new_physical_name(self):
        path = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(
            {
                "default_schema": "dbo",
                "tables": {
                    "faculty": {
                        "physical": "HR_Staff",
                        "columns": {"department_id": "DeptCode"},
                    }
                },
            },
            path,
        )
        path.close()
        self.addCleanup(os.unlink, path.name)

        tables, default_schema = schema_map._load(path.name)
        self.assertEqual(default_schema, "dbo")
        self.assertEqual(tables["faculty"]["physical"], "HR_Staff")
        self.assertEqual(tables["faculty"]["schema"], "dbo")
        self.assertEqual(tables["faculty"]["columns"]["department_id"], "DeptCode")

    def test_unmapped_columns_pass_through(self):
        # Introspection discovers real column names; the map only needs entries
        # for columns the code names literally.
        self.assertEqual(schema_map.physical_column("faculty", "email"), "email")
