# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts import sessions


class Command(BaseCommand):
    help = (
        "Deactivate an account and destroy its live sessions. Use when someone "
        "leaves the institute. Deactivation is preferred over deletion: it keeps "
        "the audit trail of what that account asked intact."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--reactivate", action="store_true",
            help="Re-enable a previously disabled account instead.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            raise CommandError(f"No such user: {username!r}") from None

        if options["reactivate"]:
            user.is_active = True
            user.save(update_fields=["is_active"])
            self.stdout.write(self.style.SUCCESS(f"Reactivated {user.username}."))
            return

        user.is_active = False
        user.save(update_fields=["is_active"])

        # Setting is_active=False stops future LOGINS, but an already-established
        # session cookie would keep working until it expires. DRF's
        # SessionAuthentication does re-check is_active, so this is belt and
        # braces — but relying on that alone would leave any future
        # authentication class as a hole.
        #
        # This WAS a scan of the django_session table, which returned zero the
        # moment sessions moved to Redis — silently revoking nothing while
        # reporting success. accounts/sessions.revoke_all handles both stores.
        killed = sessions.revoke_all(user)

        self.stdout.write(self.style.SUCCESS(
            f"Disabled {user.username} and destroyed {killed} live session(s)."
        ))
