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

WHERE THE COUNTERS LIVE, AND WHY THEY MOVED
Redis, not Postgres. Three reasons, in order of how much they matter:

  1. A failed login used to be a WRITE to the records database. A guessing burst
     was therefore write load on the same Postgres that serves student data —
     an attacker choosing how hard to push the database is not a position to be
     in. Redis absorbs it, and the keys expire on their own.
  2. Lock state no longer depends on the database being reachable.
  3. The counter is now shared across gunicorn workers. It was already
     consistent at one worker, but the limit silently loosened per worker added.

THE DATABASE FIELDS ARE STILL WRITTEN, and are still the fallback. UserProfile
keeps `failed_login_attempts` and `locked_until` because an operator asking "is
this account locked?" should be able to see it in the database, and because if
Redis is unreachable the lock must not simply vanish. Redis is authoritative
when it answers; the profile is consulted when it does not.

    Redis up    -> Redis decides. The profile is mirrored best-effort.
    Redis down  -> the profile decides, exactly as before this change.

That ordering is deliberate: falling back to the profile FAILS CLOSED. A user
locked out a minute before a Redis outage stays locked, rather than the outage
handing an attacker a clean slate.
"""

import logging
import os

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("accounts")

MAX_FAILED_ATTEMPTS = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

# How long a partial failure count survives. Without a window, four failures
# spread over a year would lock an account on the fifth — punishing ordinary
# forgetfulness rather than an attack. One lockout period is the natural span.
_COUNTER_TTL_SECONDS = LOCKOUT_MINUTES * 60


def _fail_key(username):
    return f"login-failed:{username}"


def _lock_key(username):
    return f"login-locked-until:{username}"


def _username_of(profile):
    """The username for a profile, without assuming the relation is loaded.

    Guards the case where the caller passes a profile whose user row cannot be
    fetched — during a database outage, for instance.
    """
    try:
        return profile.user.username
    except Exception:
        return ""


def is_locked(profile):
    """True if this account is currently locked.

    Expiry is evaluated on read rather than by a scheduled job — there is no
    scheduler here, and a lock that only lifts when something sweeps it would
    become permanent the moment that sweep stopped running. In Redis the key's
    TTL does this for free; the profile branch keeps the original behaviour.
    """
    username = _username_of(profile)
    try:
        locked_until = cache.get(_lock_key(username)) if username else None
        if locked_until is not None:
            if timezone.now() < locked_until:
                return True
            # TTL should have removed this already; tidy up and carry on.
            cache.delete(_lock_key(username))
            return False
        # Not locked according to Redis. Redis is authoritative when it answers,
        # so do NOT fall through to a stale profile value here — that would
        # resurrect a lock the TTL has legitimately expired.
        return False
    except Exception as exc:
        logger.warning(
            "lockout: cache unavailable (%s) — falling back to the profile for %r",
            exc, username,
        )

    if profile.locked_until is None:
        return False
    if timezone.now() >= profile.locked_until:
        try:
            profile.locked_until = None
            profile.failed_login_attempts = 0
            profile.save(update_fields=["locked_until", "failed_login_attempts"])
        except Exception:
            logger.exception("could not clear an expired lock for %r", username)
        return False
    return True


def seconds_remaining(profile):
    username = _username_of(profile)
    try:
        locked_until = cache.get(_lock_key(username)) if username else None
        if locked_until is not None:
            return max(0, int((locked_until - timezone.now()).total_seconds()))
    except Exception:
        pass
    if profile.locked_until is None:
        return 0
    return max(0, int((profile.locked_until - timezone.now()).total_seconds()))


def _mirror(profile, attempts, locked_until):
    """Copy the authoritative state into the profile, best-effort.

    For operator visibility and as the fallback source. A failure here — the
    database being down, which is now a survivable condition — must not stop
    the lockout working, so it is logged and swallowed.
    """
    try:
        profile.failed_login_attempts = attempts
        profile.locked_until = locked_until
        profile.save(update_fields=["failed_login_attempts", "locked_until"])
    except Exception as exc:
        logger.warning("lockout: could not mirror state to the database: %s", exc)


def record_failure(profile, username, client_ip):
    """Count a failed attempt and lock the account if it has run out."""
    attempts = None
    try:
        key = _fail_key(username)
        # add() then incr() rather than get/set: incr is atomic in Redis, so two
        # simultaneous wrong guesses cannot both read 3 and both write 4,
        # letting an attacker have more tries than the policy allows.
        cache.add(key, 0, _COUNTER_TTL_SECONDS)
        attempts = cache.incr(key)
    except Exception as exc:
        logger.warning("lockout: cache unavailable (%s) — counting in the database", exc)
        attempts = (profile.failed_login_attempts or 0) + 1

    locked_until = None
    if attempts >= MAX_FAILED_ATTEMPTS:
        locked_until = timezone.now() + timezone.timedelta(minutes=LOCKOUT_MINUTES)
        try:
            cache.set(_lock_key(username), locked_until, LOCKOUT_MINUTES * 60)
        except Exception:
            pass  # the profile mirror below still records it
        logger.warning(
            "ACCOUNT LOCKED username=%r after %d failed attempts, until %s (ip=%s)",
            username, attempts, locked_until, client_ip,
        )
    else:
        logger.info(
            "failed login %d/%d username=%r ip=%s",
            attempts, MAX_FAILED_ATTEMPTS, username, client_ip,
        )

    _mirror(profile, attempts, locked_until)


def record_success(profile):
    """Clear the counter after a genuine login."""
    username = _username_of(profile)
    try:
        cache.delete_many([_fail_key(username), _lock_key(username)])
    except Exception as exc:
        logger.warning("lockout: could not clear cache counters: %s", exc)

    if profile.failed_login_attempts or profile.locked_until:
        _mirror(profile, 0, None)


def clear(username, profile=None):
    """Unlock an account administratively. Used by the unlock_user command."""
    try:
        cache.delete_many([_fail_key(username), _lock_key(username)])
    except Exception as exc:
        logger.warning("lockout: could not clear cache counters: %s", exc)
    if profile is not None:
        _mirror(profile, 0, None)
    logger.warning("ACCOUNT UNLOCKED username=%r (administrative)", username)
