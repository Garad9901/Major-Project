# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand, CommandError

from ._provision import ProvisionError, provision_user


class Command(BaseCommand):
    help = (
        "Create one user account with a randomly generated initial password. "
        "The account is flagged must_change_password, so the password below is "
        "usable exactly once."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", required=True, choices=["staff", "student"])
        parser.add_argument("--email", default="")
        parser.add_argument("--full-name", default="")
        parser.add_argument("--created-by", default="")

    def handle(self, *args, **options):
        try:
            user, password = provision_user(
                username=options["username"],
                role=options["role"],
                email=options["email"],
                full_name=options["full_name"],
                created_by=options["created_by"],
            )
        except ProvisionError as exc:
            raise CommandError(str(exc)) from None

        # This command prints ONE password to the terminal, unlike import_users
        # which writes to a 0600 file. That is a deliberate trade-off: creating a
        # single account is an interactive act where the operator needs the value
        # immediately, and a one-account credentials file is friction that leads
        # to operators inventing their own worse workaround. The warning below
        # exists because the value WILL be in terminal scrollback.
        self.stdout.write(self.style.SUCCESS(f"Created {user.username} ({options['role']})."))
        self.stdout.write("")
        self.stdout.write(f"  Initial password: {password}")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "This password is now in your terminal scrollback. Give it to its owner "
            "over a private channel, then clear your screen. They must change it at "
            "first login before they can use the assistant."
        ))
