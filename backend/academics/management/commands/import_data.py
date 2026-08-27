# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Import a college's own records from CSV.

    python manage.py import_data --entity departments --file departments.csv --dry-run
    python manage.py import_data --entity departments --file departments.csv --apply
    python manage.py import_data --list
    python manage.py import_data --entity students --template > students.csv

DRY RUN IS THE DEFAULT, AND --apply IS REQUIRED TO WRITE. The first thing anyone
does with a new importer is point it at real data; making the safe thing the
default costs one flag and prevents one very bad afternoon.
"""

import sys

from django.core.management.base import BaseCommand, CommandError

from academics import importers
from orchestrator import cache


class Command(BaseCommand):
    help = (
        "Import academic records from a CSV file. Validates everything first, "
        "reports every problem with its line number, and writes nothing unless "
        "--apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", choices=importers.ENTITIES, help="What is being imported.")
        parser.add_argument("--file", help="Path to the CSV. Use '-' for stdin.")
        parser.add_argument(
            "--apply", action="store_true",
            help="Actually write the rows. Without this, nothing is saved.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Explicit no-op flag; this is already the default.",
        )
        parser.add_argument("--list", action="store_true", help="List importable entities.")
        parser.add_argument(
            "--template", action="store_true",
            help="Print a header row and one example row for --entity, then exit.",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self._list()
            return

        entity = options["entity"]
        if not entity:
            raise CommandError("--entity is required. Use --list to see the options.")

        if options["template"]:
            self.stdout.write(importers.SPECS[entity]["example"])
            return

        path = options["file"]
        if not path:
            raise CommandError("--file is required (or '-' to read from stdin).")

        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply and --dry-run contradict each other. Pick one.")

        dry_run = not options["apply"]

        try:
            if path == "-":
                result = importers.run_import(entity, sys.stdin, dry_run=dry_run)
            else:
                with open(path, "rb") as handle:
                    result = importers.run_import(entity, handle, dry_run=dry_run)
        except FileNotFoundError:
            raise CommandError(f"no such file: {path}")
        except importers.ImportError_ as exc:
            raise CommandError(str(exc))

        self._report(result, dry_run)

        # Non-zero exit so a provisioning script can branch on it. A silent
        # failure in an automated import is how a college discovers at
        # enrolment that half their students are missing.
        if not result.ok:
            raise CommandError(
                f"{len(result.errors)} problem(s) found — nothing was written."
            )

        # CLEAR CACHED ANSWERS, because the records they were computed from have
        # just changed.
        #
        # Without this, correcting a fee or a deadline and re-importing leaves
        # students being told the old figure for up to RESPONSE_CACHE_TTL_SECONDS
        # — and because answers are matched SEMANTICALLY, rephrasing the question
        # does not escape the stale entry. That is the worst outcome this system
        # has: a confident, wrong, specific number.
        #
        # Only on a real write. A dry run changed nothing, and clearing the
        # cache after one would throw away good entries for no reason.
        if not dry_run and (result.created or result.updated):
            token = cache.bump_generation(f"import:{entity}")
            if token is None:
                # Never claim the cache was cleared when it was not. The import
                # itself SUCCEEDED and is committed, so this is a warning about
                # what students will see, not an error about the data.
                self.stdout.write(self.style.WARNING(
                    "\n  WARNING: the records were imported, but cached answers "
                    "could NOT be cleared (Redis unreachable)."
                ))
                self.stdout.write(self.style.WARNING(
                    "  Users may keep receiving pre-import answers for up to "
                    "RESPONSE_CACHE_TTL_SECONDS. Run `manage.py "
                    "clear_answer_cache` once Redis is back."
                ))
            else:
                self.stdout.write(
                    "\n  Cached answers cleared — the next question is answered "
                    "from the new records."
                )

    def _list(self):
        self.stdout.write("Importable entities:\n")
        for name in importers.ENTITIES:
            spec = importers.SPECS[name]
            required = ", ".join(spec["required"])
            self.stdout.write(f"\n  {name}")
            self.stdout.write(f"      required columns : {required}")
            self.stdout.write(f"      matched on       : {' + '.join(spec['key'])}")
        self.stdout.write(
            "\nColumn names are matched case- and separator-insensitively, so "
            "'Roll Number', 'roll_number' and 'ROLL-NUMBER' are the same column.\n"
            "\nImport order matters where one entity references another:\n"
            "    departments -> programs -> courses / faculty -> students -> fee_structures\n"
        )

    def _report(self, result, dry_run):
        head = "DRY RUN — nothing was written" if dry_run else "APPLIED"
        self.stdout.write(f"\n{head}")
        self.stdout.write(f"  entity        : {result.entity}")
        self.stdout.write(f"  rows in file  : {result.total_rows}")

        if result.errors:
            self.stdout.write(self.style.ERROR(f"  problems      : {len(result.errors)}"))
            self.stdout.write("")
            # Capped, because a wrong column mapping produces one error per row
            # and 900 of them buries the one line that explains the cause.
            for error in result.errors[:50]:
                self.stdout.write(self.style.ERROR(f"    {error}"))
            if len(result.errors) > 50:
                self.stdout.write(
                    self.style.ERROR(f"    ... and {len(result.errors) - 50} more")
                )
            self.stdout.write(
                "\n  Nothing was written. Fix the file and run again — the "
                "importer matches on an existing record's natural key, so "
                "re-running a corrected file updates rather than duplicates."
            )
            return

        verb = "would be created" if dry_run else "created"
        self.stdout.write(self.style.SUCCESS(f"  {verb:<14}: {result.created}"))
        verb = "would be updated" if dry_run else "updated"
        self.stdout.write(self.style.SUCCESS(f"  {verb:<14}: {result.updated}"))
        self.stdout.write(f"  unchanged     : {result.unchanged}")

        if dry_run:
            self.stdout.write(
                "\n  Re-run with --apply to write these changes."
            )
