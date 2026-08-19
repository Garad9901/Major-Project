# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Guards on the CSV import path.

The properties that matter here are the ones a buyer's data will find:

  * a dry run writes NOTHING, and reports what the real run would do
  * a file with any error writes nothing at all — never half of it
  * re-running a corrected file updates rather than duplicating
  * an ambiguous date is refused, not guessed
  * export and import are the same shape, so the round trip works

The dry-run/real-run equivalence is the one worth being strict about. A dry run
that validated less than the real run would be actively harmful: it would tell
an operator their file was fine and then fail halfway through writing it.
"""

import io

from django.test import TestCase

from academics import importers
from academics.models import Department, Faculty


def run(entity, text, dry_run=True):
    return importers.run_import(entity, io.StringIO(text), dry_run=dry_run)


class DryRunWritesNothingTests(TestCase):
    CSV = "name,code,established_year\nCivil Engineering,CE,1985\nElectrical,EE,1990\n"

    def test_dry_run_reports_what_would_happen(self):
        result = run("departments", self.CSV)
        self.assertTrue(result.ok)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.total_rows, 2)

    def test_dry_run_leaves_the_database_untouched(self):
        run("departments", self.CSV)
        self.assertEqual(Department.objects.filter(code__in=["CE", "EE"]).count(), 0)

    def test_apply_writes(self):
        run("departments", self.CSV, dry_run=False)
        self.assertEqual(Department.objects.filter(code__in=["CE", "EE"]).count(), 2)


class UpsertOnNaturalKeyTests(TestCase):
    """Re-running a corrected file must not duplicate. An operator WILL run the
    same file twice; the only question is whether that is safe."""

    CSV = "name,code,established_year\nCivil Engineering,CE,1985\n"

    def test_rerunning_the_same_file_changes_nothing(self):
        run("departments", self.CSV, dry_run=False)
        result = run("departments", self.CSV, dry_run=False)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.unchanged, 1)
        self.assertEqual(Department.objects.filter(code="CE").count(), 1)

    def test_a_changed_value_updates_in_place(self):
        run("departments", self.CSV, dry_run=False)
        result = run("departments", self.CSV.replace("1985", "1986"), dry_run=False)
        self.assertEqual(result.updated, 1)
        self.assertEqual(Department.objects.get(code="CE").established_year, 1986)


class NothingIsWrittenWhenAnyRowFailsTests(TestCase):
    """All-or-nothing. A partial import leaves the operator to work out which
    half landed, which is worse than a clean failure."""

    def test_one_bad_row_blocks_the_whole_file(self):
        csv_text = (
            "name,code,established_year\n"
            "Civil Engineering,CE,1985\n"
            "Electrical Engineering,EE,not-a-year\n"
        )
        result = run("departments", csv_text, dry_run=False)
        self.assertFalse(result.ok)
        self.assertEqual(Department.objects.filter(code="CE").count(), 0)

    def test_every_error_is_reported_not_just_the_first(self):
        csv_text = (
            "name,code,established_year\n"
            "A,A1,bad\n"
            "B,B1,worse\n"
            "C,C1,terrible\n"
        )
        result = run("departments", csv_text)
        self.assertEqual(len(result.errors), 3)

    def test_errors_carry_the_spreadsheet_line_number(self):
        """Header is line 1, so the first data row is line 2 — the number the
        operator sees when they press ctrl-G."""
        result = run("departments", "name,code,established_year\nA,A1,bad\n")
        self.assertEqual(result.errors[0].line, 2)


class ColumnNamesAreForgivingTests(TestCase):
    def test_case_and_separators_do_not_matter(self):
        """'Name', 'CODE' and 'Established Year' must all match."""
        result = run("departments", "Name,CODE,Established Year\nX,X1,2000\n")
        self.assertTrue(result.ok, [str(e) for e in result.errors])
        self.assertEqual(result.created, 1)

    def test_surrounding_whitespace_in_a_header_is_ignored(self):
        result = run("departments", " Name , Code \nX,X1\n")
        self.assertTrue(result.ok, [str(e) for e in result.errors])

    def test_a_missing_required_column_names_it_and_shows_the_format(self):
        with self.assertRaises(importers.ImportError_) as caught:
            run("departments", "Department Name,CODE\nX,X1\n")
        message = str(caught.exception)
        self.assertIn("name", message)
        self.assertIn("Expected format", message)

    def test_excel_byte_order_mark_is_stripped(self):
        """Excel writes a BOM. Without handling it the first header becomes
        '﻿name' and every row fails on a missing required column."""
        result = importers.run_import(
            "departments",
            io.BytesIO("name,code\nBOM Test,BOM1\n".encode("utf-8-sig")),
        )
        self.assertTrue(result.ok, [str(e) for e in result.errors])
        self.assertEqual(result.created, 1)


class AmbiguousDatesAreRefusedTests(TestCase):
    """A date that imports cleanly and is wrong by a month is worse than one
    that fails. This data is stated to students as fact."""

    def setUp(self):
        Department.objects.create(name="Civil Engineering", code="CE")

    def _faculty_csv(self, date):
        return (
            "first_name,last_name,email,department,joined_date\n"
            f"A,B,a.b@example.edu,CE,{date}\n"
        )

    def test_ambiguous_slash_date_is_rejected(self):
        result = run("faculty", self._faculty_csv("03/04/2026"))
        self.assertFalse(result.ok)
        self.assertIn("ambiguous", str(result.errors[0]))

    def test_unambiguous_day_first_date_is_accepted(self):
        result = run("faculty", self._faculty_csv("25/12/2025"))
        self.assertTrue(result.ok, [str(e) for e in result.errors])

    def test_iso_is_always_accepted(self):
        result = run("faculty", self._faculty_csv("2026-04-03"))
        self.assertTrue(result.ok, [str(e) for e in result.errors])


class ForeignKeysResolveByHumanValueTests(TestCase):
    """Nobody exporting from their SIS knows our Department.id."""

    def setUp(self):
        Department.objects.create(name="Civil Engineering", code="CE")

    def test_resolved_by_code(self):
        result = run("faculty", "first_name,last_name,email,department\nA,B,a@x.edu,CE\n")
        self.assertTrue(result.ok, [str(e) for e in result.errors])

    def test_resolved_by_full_name_case_insensitively(self):
        result = run(
            "faculty",
            "first_name,last_name,email,department\nA,B,a@x.edu,civil engineering\n",
        )
        self.assertTrue(result.ok, [str(e) for e in result.errors])

    def test_an_unknown_department_says_what_to_do(self):
        result = run("faculty", "first_name,last_name,email,department\nA,B,a@x.edu,NOPE\n")
        self.assertFalse(result.ok)
        self.assertIn("Import departments first", str(result.errors[0]))

    def test_one_root_cause_produces_one_error(self):
        """A failed lookup used to ALSO report 'is required but empty',
        doubling the apparent problem count on a large file."""
        result = run("faculty", "first_name,last_name,email,department\nA,B,a@x.edu,NOPE\n")
        self.assertEqual(len(result.errors), 1, [str(e) for e in result.errors])


class DuplicatesWithinOneFileAreReportedTests(TestCase):
    def test_same_natural_key_twice(self):
        csv_text = "name,code\nA,DUP\nB,DUP\n"
        result = run("departments", csv_text)
        self.assertFalse(result.ok)
        self.assertIn("duplicates line 2", str(result.errors[0]))


class RoundTripTests(TestCase):
    """What export_data writes must be what import_data reads. An import path
    with no working export is lock-in."""

    def test_export_then_import_is_a_no_op(self):
        from django.core.management import call_command

        Department.objects.create(name="Civil Engineering", code="CE", established_year=1985)
        Department.objects.create(name="Electrical", code="EE", established_year=1990)

        buffer = io.StringIO()
        call_command("export_data", "--entity", "departments", stdout=buffer)

        result = run("departments", buffer.getvalue(), dry_run=False)
        self.assertTrue(result.ok, [str(e) for e in result.errors])
        self.assertEqual(result.created, 0)
        self.assertEqual(result.unchanged, 2)

    def test_faculty_round_trip_preserves_the_department(self):
        from django.core.management import call_command

        dept = Department.objects.create(name="Civil Engineering", code="CE")
        Faculty.objects.create(
            first_name="Asha", last_name="Menon",
            email="a.menon@example.edu", department=dept,
        )
        buffer = io.StringIO()
        call_command("export_data", "--entity", "faculty", stdout=buffer)
        self.assertIn("CE", buffer.getvalue())

        result = run("faculty", buffer.getvalue(), dry_run=False)
        self.assertTrue(result.ok, [str(e) for e in result.errors])
        self.assertEqual(result.unchanged, 1)
