# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Operator-driven password reset — the "forgot password" flow.

WHY THERE IS NO EMAIL LINK
A self-service reset needs a channel to send the link over, and this deployment
may have no outbound email. A reset link with nowhere to go is not a feature.
More importantly, an email-based reset would become the weakest way into an
account holding student records: it moves the security of every account onto
whatever mailbox is listed against it.

So a reset is a deliberate act by an operator who has already identified the
person by some means outside this system.

WHAT IT DOES
  * generates a fresh random password (never one the operator chose)
  * requires it to be changed at next login
  * deletes the account's session rows

ON SESSIONS — CORRECTED BY TEST
This command originally offered a --keep-sessions flag, on the belief that
changing a password leaves existing sessions signed in. That belief is WRONG,
and the test proved it: Django stores a hash of the password inside the session
and AuthenticationMiddleware re-checks it on every request, so changing the
password invalidates every existing session by itself. The flag promised
something it could not deliver, so it is gone.

Deleting the rows is still worth doing — it frees the session table immediately
instead of leaving dead rows until their expiry — but it is housekeeping, not
the security control. The security control is Django's, and it is automatic.
"""

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import profile_for

from ._provision import generate_initial_password


class Command(BaseCommand):
    help = (
        "Reset one user's password to a new random value, force a change at "
        "next login, and end their existing sessions."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def _kill_sessions(self, user):
        """End every active session for this user.

        Django has no user->session index, so this walks unexpired sessions and
        decodes each one. Fine for 50 users; it would need a session model with
        a user FK at a much larger scale.
        """
        killed = 0
        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            try:
                data = session.get_decoded()
            except Exception:
                continue  # corrupt or unreadable — leave it to expire
            if str(data.get("_auth_user_id")) == str(user.pk):
                session.delete()
                killed += 1
        return killed

    def handle(self, *args, **options):
        username = options["username"]
        user = User.objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"no such user: {username!r}")

        password = generate_initial_password()
        user.set_password(password)
        user.save(update_fields=["password"])

        profile = profile_for(user)
        profile.must_change_password = True
        profile.save(update_fields=["must_change_password"])

        killed = self._kill_sessions(user)

        self.stdout.write(self.style.SUCCESS(f"Password reset for '{username}'."))
        self.stdout.write("")
        self.stdout.write(f"  Temporary password: {password}")
        self.stdout.write("")
        self.stdout.write(
            "This password is now in your terminal scrollback. Give it to its "
            "owner over a channel you trust, then clear your screen."
        )
        self.stdout.write(
            "They must change it at first login before they can ask anything."
        )
        self.stdout.write(
            f"  Cleared {killed} session row(s). Django had already invalidated "
            f"them when the password changed; this just tidies the table."
        )
