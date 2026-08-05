# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Delete audit rows past the retention period.

The audit log holds the question text, username and client IP for every request
made against a database of real student records. That is personal data with an
indefinite growth curve, so it is bounded by time and then removed.

Retention is AUDIT_LOG_RETENTION_DAYS (default 90, env-configurable). Run this
on a schedule — deletion that depends on someone remembering is not a retention
policy.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from audit.models import AuditLog


class Command(BaseCommand):
    help = (
        "Delete audit log entries older than AUDIT_LOG_RETENTION_DAYS "
        "(default 90). Use --dry-run to see what would go."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Override the retention period for this run only.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be deleted without deleting it.",
        )

    def handle(self, *args, **options):
        days = options["days"] if options["days"] is not None else settings.AUDIT_LOG_RETENTION_DAYS

        if days <= 0:
            # Guard against AUDIT_LOG_RETENTION_DAYS=0 being read as "keep
            # nothing" and silently wiping the entire audit trail.
            self.stderr.write(self.style.ERROR(
                f"Refusing to run with a retention of {days} days. "
                f"A value of 0 or less would delete the entire audit log. "
                f"To disable purging, simply do not schedule this command."
            ))
            return

        cutoff = timezone.now() - timezone.timedelta(days=days)
        queryset = AuditLog.objects.filter(created_at__lt=cutoff)
        count = queryset.count()
        total = AuditLog.objects.count()

        if options["dry_run"]:
            oldest = AuditLog.objects.order_by("created_at").values_list("created_at", flat=True).first()
            self.stdout.write(
                f"DRY RUN — retention {days} days (cutoff {cutoff:%Y-%m-%d %H:%M} UTC)\n"
                f"  total entries    : {total}\n"
                f"  would be deleted : {count}\n"
                f"  would remain     : {total - count}\n"
                f"  oldest entry     : {oldest:%Y-%m-%d %H:%M} UTC" if oldest else "  oldest entry     : (none)"
            )
            return

        if count == 0:
            self.stdout.write(f"Nothing to purge — no entries older than {days} days.")
            return

        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Purged {deleted} audit entries older than {days} days "
            f"(cutoff {cutoff:%Y-%m-%d %H:%M} UTC). {total - count} remain."
        ))
