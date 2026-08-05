# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


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
        killed = 0
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
                session.delete()
                killed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Disabled {user.username} and destroyed {killed} live session(s)."
        ))
