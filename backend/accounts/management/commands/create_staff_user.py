# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Ensure a BOOTSTRAP administrator account exists.

This is not "the shared staff account" any more. Now that per-user accounts
exist (`create_user`, `import_users`), this command has exactly one job: make
sure a fresh server has one account that can log in and provision the real ones.
Everybody else gets their own account.

WHY THIS NO LONGER RESETS THE PASSWORD ON EVERY START
It used to call set_password() unconditionally, on every single backend start.
Two things followed, both bad:

  1. An operator who changed this password from inside the application had it
     SILENTLY REVERTED to the .env value at the next restart — including a
     restart triggered by an unrelated deploy. The account's effective password
     became whatever sat in a file on disk, permanently.

  2. It made `must_change_password` unusable for this account, because the flag
     could never be satisfied: change the password, restart, the environment
     value returns. accounts/models.profile_for still describes that loop as the
     reason legacy accounts are exempted — this command is what caused it.

So the password is written ONLY when the account is first created. On every
later start this command confirms the account exists and touches nothing else.
Use --reset-password for the deliberate "the operator is locked out" case.
"""

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from accounts.models import ROLE_STAFF, UserProfile, ensure_groups


class Command(BaseCommand):
    help = (
        "Ensure the bootstrap administrator account exists. Creates it on first "
        "run only; never silently changes an existing account's password. "
        "Use --reset-password to deliberately reset it."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("STAFF_USERNAME", "staff"))
        parser.add_argument("--password", default=os.getenv("STAFF_PASSWORD", "staffpass123"))
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help=(
                "Reset the existing account's password to STAFF_PASSWORD and require "
                "a change at next login. For lockout recovery — not for routine starts."
            ),
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        # In production the bootstrap password was read out of a file by whoever
        # deployed the server, so it is a shared secret until the operator
        # replaces it — force that replacement. In development the documented
        # login (see README) is meant to work immediately, so it is not forced;
        # that keeps the local workflow unchanged.
        is_production = os.getenv("DJANGO_ENV", "development").strip().lower() == "production"

        user = User.objects.filter(username=username).first()

        if user is None:
            user = User.objects.create_user(username=username, password=password)
            user.is_staff = True
            user.save()
            user.groups.add(ensure_groups()[ROLE_STAFF])
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "must_change_password": is_production,
                    "created_by": "bootstrap",
                },
            )
            self.stdout.write(self.style.SUCCESS(
                f"Created bootstrap account '{username}'."
                + (" It must change its password at first login." if is_production else "")
            ))
            return

        if options["reset_password"]:
            user.set_password(password)
            user.is_staff = True
            user.save()
            user.groups.add(ensure_groups()[ROLE_STAFF])
            UserProfile.objects.update_or_create(
                user=user, defaults={"must_change_password": True},
            )
            self.stdout.write(self.style.WARNING(
                f"Password for '{username}' RESET to STAFF_PASSWORD. "
                f"It must be changed at next login."
            ))
            return

        # The normal path on every restart: confirm, and change nothing.
        self.stdout.write(
            f"Bootstrap account '{username}' already exists; password left unchanged."
        )
