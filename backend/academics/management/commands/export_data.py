# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Export academic records to CSV.

    python manage.py export_data --entity departments            # to stdout
    python manage.py export_data --entity students --out s.csv
    python manage.py export_data --all --out-dir ./export

WHY THIS EXISTS, AND WHY IT MATTERS COMMERCIALLY
A buyer will ask "can we get our data back out". The honest answer has to be yes,
in a format they can open, without us. An import path with no export is a lock-in
that nobody should agree to and no procurement process should approve.

It also closes the loop on the importer: what this writes is exactly what
import_data reads, so an export can be edited in a spreadsheet and imported
back. That round trip is tested (academics/test_import.py).

WHAT IS NOT EXPORTED HERE
Nothing that identifies a student's performance or money: attendance, exam
results and fee payments are deliberately absent. They are exportable through a
direct database dump by someone who has decided that is appropriate, which is a
different and more deliberate act than running a management command. See
SECURITY.md on what the read-only role can and cannot see.
"""

import csv
import io
import os

from django.core.management.base import BaseCommand, CommandError

from academics import importers


def _row_for(entity, instance):
    """Flatten one record to the same column names import_data accepts."""
    spec = importers.SPECS[entity]
    row = {}
    for column in spec["fields"]:
        value = getattr(instance, column, None)
        row[column] = "" if value is None else str(value)
    for column in spec["refs"]:
        related = getattr(instance, column, None)
        if related is None:
            row[column] = ""
        else:
            # Export the CODE for departments and the NAME for everything else —
            # matching what the corresponding resolver accepts, so the output
            # imports back without an edit.
            row[column] = getattr(related, "code", None) or getattr(related, "name", "")
    return row


class Command(BaseCommand):
    help = "Export academic records to CSV in the same shape import_data reads."

    def add_arguments(self, parser):
        parser.add_argument("--entity", choices=importers.ENTITIES)
        parser.add_argument("--all", action="store_true", help="Export every entity.")
        parser.add_argument("--out", help="Write to this file instead of stdout.")
        parser.add_argument("--out-dir", help="With --all: directory to write one CSV per entity.")

    def handle(self, *args, **options):
        if options["all"]:
            out_dir = options["out_dir"]
            if not out_dir:
                raise CommandError("--all needs --out-dir.")
            os.makedirs(out_dir, exist_ok=True)
            total = 0
            # Written in dependency order, so re-importing the directory in
            # `ls` order works: a department exists before the faculty row that
            # references it.
            for entity in _IMPORT_ORDER:
                path = os.path.join(out_dir, f"{entity}.csv")
                with open(path, "w", newline="", encoding="utf-8") as handle:
                    count = self._write(entity, handle)
                total += count
                self.stdout.write(f"  {entity:<16} {count:>6} row(s) -> {path}")
            self.stdout.write(self.style.SUCCESS(f"\nExported {total} row(s) to {out_dir}"))
            self.stdout.write(
                "Files are numbered by dependency order in DATA_IMPORT.md; import "
                "departments before anything that references one."
            )
            return

        entity = options["entity"]
        if not entity:
            raise CommandError("--entity is required (or --all with --out-dir).")

        if options["out"]:
            with open(options["out"], "w", newline="", encoding="utf-8") as handle:
                count = self._write(entity, handle)
            self.stdout.write(self.style.SUCCESS(f"{count} row(s) -> {options['out']}"))
        else:
            # Written into a buffer and emitted through self.stdout rather than
            # to sys.stdout directly. Django's OutputWrapper is what
            # call_command(stdout=...) redirects, so writing to sys.stdout makes
            # the command untestable — and the round-trip test is the one that
            # proves export and import agree. ending="" because csv already
            # supplies the line terminators.
            #
            # Returns nothing: Django prints a command's return value, so
            # returning the row count made it try str.endswith() on an int.
            buffer = io.StringIO()
            self._write(entity, buffer)
            self.stdout.write(buffer.getvalue(), ending="")

    def _write(self, entity, handle):
        spec = importers.SPECS[entity]
        columns = list(spec["fields"]) + list(spec["refs"])
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()

        queryset = spec["model"].objects.all()
        if spec["refs"]:
            queryset = queryset.select_related(*spec["refs"])

        count = 0
        for instance in queryset.iterator():
            writer.writerow(_row_for(entity, instance))
            count += 1
        return count


# Dependency order. departments has no dependencies; fee_structures needs
# programs, which need departments.
_IMPORT_ORDER = [
    "departments",
    "rooms",
    "programs",
    "courses",
    "faculty",
    "students",
    "fee_structures",
]
