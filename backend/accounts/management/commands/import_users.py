# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Bulk-create accounts from a roster CSV.

The credentials file this writes is the sensitive artefact, not the input. It is
created with 0600 permissions and is never echoed to the terminal, because
terminal scrollback and shell history outlive the session that produced them.
"""

import csv
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ensure_groups

from ._provision import ProvisionError, provision_user

REQUIRED_COLUMNS = {"username", "role"}


class Command(BaseCommand):
    help = (
        "Bulk-create user accounts from a CSV with columns: "
        "username,role[,email,full_name]. Generates a random initial password "
        "for each and writes them to a credentials file with 0600 permissions. "
        "Every account is flagged must_change_password."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Roster CSV to import.")
        parser.add_argument(
            "--output", default=None,
            help="Credentials file to write (default: <csv_path>.credentials.csv).",
        )
        parser.add_argument(
            "--created-by", default="",
            help="Name of the operator running the import, recorded on each profile.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Validate the CSV and report what would happen, creating nothing.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        if not os.path.exists(csv_path):
            raise CommandError(f"CSV not found: {csv_path}")

        output_path = options["output"] or f"{csv_path}.credentials.csv"
        dry_run = options["dry_run"]

        if not dry_run and os.path.exists(output_path):
            raise CommandError(
                f"{output_path} already exists. Refusing to overwrite a credentials "
                f"file — move or delete it first."
            )

        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            fieldnames = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
            missing = REQUIRED_COLUMNS - fieldnames
            if missing:
                raise CommandError(
                    f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                    f"Found: {', '.join(sorted(fieldnames)) or '(none)'}"
                )
            rows = [
                {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                for row in reader
            ]

        if not rows:
            raise CommandError("CSV contains no data rows.")

        groups = ensure_groups()
        created = []
        failures = []

        # One transaction for the whole import: a roster that fails halfway
        # leaves an operator unsure which half exists. All or nothing.
        try:
            with transaction.atomic():
                for line_no, row in enumerate(rows, start=2):  # line 1 is the header
                    try:
                        user, password = provision_user(
                            username=row.get("username"),
                            role=row.get("role"),
                            email=row.get("email", ""),
                            full_name=row.get("full_name", ""),
                            created_by=options["created_by"],
                            groups=groups,
                        )
                        created.append((user.username, row.get("role", ""), password))
                    except ProvisionError as exc:
                        failures.append((line_no, row.get("username", "?"), str(exc)))

                if failures:
                    raise _Rollback()

                if dry_run:
                    raise _Rollback()
        except _Rollback:
            pass

        if failures:
            self.stderr.write(self.style.ERROR(f"Import ABORTED — {len(failures)} problem(s). No accounts created:"))
            for line_no, username, msg in failures:
                self.stderr.write(f"  line {line_no}: {username}: {msg}")
            raise CommandError("Fix the CSV and re-run. Nothing was changed.")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN OK — {len(created)} account(s) would be created. Nothing was written."
            ))
            return

        self._write_credentials(output_path, created)

        self.stdout.write(self.style.SUCCESS(f"Created {len(created)} account(s)."))
        self.stdout.write(f"Initial passwords written to: {output_path} (permissions 0600)")
        self.stdout.write("")
        self.stdout.write("No password has been printed here. Next steps:")
        self.stdout.write("  1. Distribute each password to its owner over a private channel.")
        self.stdout.write("  2. Every account must change its password at first login.")
        self.stdout.write(f"  3. Securely delete {output_path} once distribution is complete.")

    def _write_credentials(self, path, created):
        # Create private, THEN write — no window in which it is world-readable.
        old_umask = os.umask(0o077)
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["username", "role", "initial_password"])
                writer.writerows(created)
        finally:
            os.umask(old_umask)
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Windows/NTFS has no POSIX mode bits. Not fatal, but the operator
            # should know the file is not protected by permissions there.
            self.stderr.write(self.style.WARNING(
                f"Could not set 0600 on {path} (non-POSIX filesystem?). "
                f"Protect this file manually."
            ))


class _Rollback(Exception):
    """Internal: forces transaction.atomic() to roll back without reporting an
    error the caller has not already handled."""
