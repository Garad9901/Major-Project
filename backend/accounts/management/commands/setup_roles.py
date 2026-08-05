# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from accounts.models import ensure_groups


class Command(BaseCommand):
    help = (
        "Idempotently create the 'staff' and 'student' role groups. Run on every "
        "backend start so a fresh database has them before any import runs."
    )

    def handle(self, *args, **options):
        groups = ensure_groups()
        self.stdout.write(self.style.SUCCESS(
            f"Roles ready: {', '.join(sorted(groups))}."
        ))
