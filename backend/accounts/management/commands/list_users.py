# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Answer the question "who can get into this system?".

Every other account command CHANGES something — create, import, reset, disable.
There was no way to simply LOOK, short of a Django shell, which meant the first
question in any access review or data-protection audit ("who has access, and
who gave it to them?") had no answer an operator could produce.

That gap is not theoretical. The reference deployment accumulated 58 accounts
during development and load testing — load00..load49, audit1, lockcontrol,
disableduser — every one of them with a known password and none of them
belonging to a person. Nobody had noticed, because nothing could show them.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import UserProfile


class Command(BaseCommand):
    help = (
        "List every account with its role, provenance and password state. "
        "Use --concerns for an access review: it reports only the accounts "
        "worth a second look and exits non-zero if it finds any."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--concerns", action="store_true",
            help=(
                "Show only accounts that warrant review, and exit 1 if any "
                "are found. Suitable for a release gate or a cron check."
            ),
        )
        parser.add_argument(
            "--staff-only", action="store_true",
            help="Only accounts with staff privileges.",
        )

    def handle(self, *args, **options):
        users = User.objects.all().order_by("username")
        if options["staff_only"]:
            users = users.filter(is_staff=True)

        profiles = {p.user_id: p for p in UserProfile.objects.all()}
        now = timezone.now()

        rows = []
        for user in users:
            profile = profiles.get(user.id)
            concerns = self._concerns(user, profile, now)
            rows.append((user, profile, concerns))

        flagged = [r for r in rows if r[2]]

        if options["concerns"]:
            self._report_concerns(flagged, len(rows))
            # A non-zero exit so this can gate a release or run from cron
            # without anyone having to read the output.
            if flagged:
                raise SystemExit(1)
            return

        self._report_all(rows)
        if flagged:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"{len(flagged)} account(s) warrant review. "
                f"Run with --concerns for detail."
            ))

    # -- classification ---------------------------------------------------------

    def _concerns(self, user, profile, now):
        """What an access review would want flagged about this account.

        Deliberately conservative: everything here is a QUESTION for the
        operator, not an assertion of a defect. An account can legitimately be
        a superuser or have no profile; the point is that somebody should have
        decided that, rather than inheriting it.
        """
        found = []

        if profile is None:
            # No profile means must_change_password cannot be enforced for
            # this account and there is no record of who created it.
            found.append("NO PROFILE — provenance unknown, password change cannot be forced")
            return found

        if user.is_superuser:
            found.append("SUPERUSER — full Django admin, including other accounts")

        if not user.is_active:
            found.append("disabled (retained for its audit trail)")

        if profile.created_by in ("", "legacy"):
            found.append(
                f"provenance {profile.created_by or 'blank'!r} — "
                f"not created by a tracked operator action"
            )

        if user.last_login is None and not profile.must_change_password:
            # The bootstrap password came out of a file somebody read. If the
            # account has never logged in AND the flag is clear, the flag was
            # cleared by something other than a user changing their password.
            found.append(
                "never logged in, yet must_change_password is CLEAR — "
                "the bootstrap password may still be live"
            )

        if profile.locked_until and profile.locked_until > now:
            found.append(f"locked out until {profile.locked_until:%Y-%m-%d %H:%M} UTC")

        return found

    # -- output -----------------------------------------------------------------

    def _report_all(self, rows):
        self.stdout.write(f"{len(rows)} account(s)")
        self.stdout.write("")
        self.stdout.write(
            f"{'username':<20} {'role':<8} {'active':<7} {'pw change':<10} "
            f"{'last login':<12} {'created by':<14}"
        )
        self.stdout.write("-" * 78)

        for user, profile, concerns in rows:
            role = "SUPER" if user.is_superuser else ("staff" if user.is_staff else "user")
            last = f"{user.last_login:%Y-%m-%d}" if user.last_login else "never"
            must = "REQUIRED" if (profile and profile.must_change_password) else "done"
            created = (profile.created_by if profile else "?") or "(blank)"

            line = (
                f"{user.username:<20} {role:<8} {str(user.is_active):<7} "
                f"{must:<10} {last:<12} {created:<14}"
            )
            if concerns:
                self.stdout.write(self.style.WARNING(line + "  <-- review"))
            else:
                self.stdout.write(line)

    def _report_concerns(self, flagged, total):
        if not flagged:
            self.stdout.write(self.style.SUCCESS(
                f"Access review: nothing flagged across {total} account(s)."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"Access review: {len(flagged)} of {total} account(s) warrant a look."
        ))
        self.stdout.write("")
        for user, _profile, concerns in flagged:
            self.stdout.write(f"  {user.username}")
            for concern in concerns:
                self.stdout.write(f"      - {concern}")
        self.stdout.write("")
        self.stdout.write(
            "None of the above is necessarily wrong. Each is something an "
            "operator should have decided rather than inherited."
        )
        self.stdout.write(
            "To remove an account that is not a person:  manage.py disable_user <name>"
        )
