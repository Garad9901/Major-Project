# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Per-account brute-force lockout: 5 failures, then 15 minutes.

WHY THIS EXISTS ALONGSIDE THE PER-IP THROTTLE
They defend against different attacks.

    per-IP throttle (10/min)   bounds how fast one source can guess.
                               Defeated by distributing the attempt: 500 hosts
                               guessing twice a minute each never trip it.
    per-account lockout        bounds how many guesses ONE ACCOUNT will accept
                               in total, from anywhere.

Neither is sufficient alone, so both run.

ON USERNAME ENUMERATION
The login view deliberately returns an identical response for "no such user",
"wrong password" and "disabled account", so an attacker cannot discover which
usernames exist. A blunt "this account is locked" message would undo that: an
attacker could lock an account with five guesses and read the different response
as confirmation the account is real.

So the lock is revealed ONLY when the supplied password is correct. Someone who
knows their own password gets a clear, useful message; someone guessing gets the
same generic rejection as always and learns nothing. That keeps both properties
at once instead of trading one for the other.
"""

import logging
import os

from django.utils import timezone

logger = logging.getLogger("accounts")

MAX_FAILED_ATTEMPTS = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))


def is_locked(profile):
    """True if this account is currently locked.

    Expiry is evaluated on read rather than by a scheduled job — there is no
    scheduler here, and a lock that only lifts when something sweeps it would
    become permanent the moment that sweep stopped running.
    """
    if profile.locked_until is None:
        return False
    if timezone.now() >= profile.locked_until:
        # Expired. Clear it so the next failure starts a fresh count.
        profile.locked_until = None
        profile.failed_login_attempts = 0
        profile.save(update_fields=["locked_until", "failed_login_attempts"])
        return False
    return True


def seconds_remaining(profile):
    if profile.locked_until is None:
        return 0
    return max(0, int((profile.locked_until - timezone.now()).total_seconds()))


def record_failure(profile, username, client_ip):
    """Count a failed attempt and lock the account if it has run out."""
    profile.failed_login_attempts += 1
    fields = ["failed_login_attempts"]

    if profile.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        profile.locked_until = timezone.now() + timezone.timedelta(minutes=LOCKOUT_MINUTES)
        fields.append("locked_until")
        logger.warning(
            "ACCOUNT LOCKED username=%r after %d failed attempts, until %s (ip=%s)",
            username, profile.failed_login_attempts, profile.locked_until, client_ip,
        )
    else:
        logger.info(
            "failed login %d/%d username=%r ip=%s",
            profile.failed_login_attempts, MAX_FAILED_ATTEMPTS, username, client_ip,
        )

    profile.save(update_fields=fields)


def record_success(profile):
    """Clear the counter after a genuine login."""
    if profile.failed_login_attempts or profile.locked_until:
        profile.failed_login_attempts = 0
        profile.locked_until = None
        profile.save(update_fields=["failed_login_attempts", "locked_until"])
