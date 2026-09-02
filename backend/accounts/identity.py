# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Who the signed-in user is, survivable across a database outage.

WHY MOVING SESSIONS TO REDIS WAS NOT ENOUGH ON ITS OWN
Cache-backed sessions mean the session COOKIE resolves without Postgres. They do
not mean the REQUEST works, because Django then does this on every single
request, in AuthenticationMiddleware:

    user_id = session["_auth_user_id"]
    request.user = backend.get_user(user_id)      # SELECT ... FROM auth_user

and this project then does one more, in CanUseAssistant:

    profile_for(user).must_change_password        # SELECT ... FROM user_profile

So with Postgres stopped, an already-signed-in user still got a 500 — measured,
after the session change, on GET /api/auth/me/. The session survived and the
request did not, which meant the orchestrator's degraded RAG path was still
unreachable in practice. This closes that last gap.

THE DESIGN: DATABASE FIRST, CACHE ONLY AS A FALLBACK
Not a read-through cache. The database is asked first, every time, and the cache
is written from the answer. The cached copy is read ONLY when the database
raises.

That ordering is the entire security argument:

  * in normal operation there is NO staleness at all — every request sees the
    live row, exactly as before this change
  * a stale identity can only ever be served while Postgres is unreachable,
    which is a state an attacker cannot induce more easily than they could
    already
  * it costs nothing in the common case beyond one cache write

The alternative (cache first, database on miss) would have been faster and would
have introduced a window in which a deactivated account still worked during
NORMAL operation. That is not a trade worth making to save a primary-key lookup.

WHAT AN ATTACKER GAINS, STATED PLAINLY
While Postgres is down, a session that was valid when the outage began stays
valid until its cached identity expires. Specifically:

  * Deactivating an account cannot take effect during the outage — but
    `manage.py disable_user` cannot run during the outage either (it needs the
    database), so nothing is actually lost.
  * The normal revocation path is UNAFFECTED. disable_user and reset_password
    both call accounts.sessions.revoke_all, which deletes the session from
    Redis. A deleted session is never authenticated, cached identity or not.

The exposure is therefore bounded by IDENTITY_TTL_SECONDS and applies only to
sessions already established before the outage started.

ON HOLDING A PASSWORD HASH IN REDIS
The cached record includes `user.password` — the PBKDF2 hash, not a password —
because Django verifies each request's session against a hash derived from it
(`get_session_auth_hash`), and without it every restored session would be
rejected as tampered. This does not meaningfully widen exposure: the same Redis
already holds live session keys, which are bearer credentials and therefore
strictly more useful to an attacker than a PBKDF2 hash.
"""

import logging

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError

logger = logging.getLogger("accounts")

# How long an identity remains usable after the database becomes unreachable.
# Long enough to ride out a restart or a failover; short enough that it is not a
# way to keep using a revoked account for an afternoon.
IDENTITY_TTL_SECONDS = int(__import__("os").getenv("IDENTITY_CACHE_SECONDS", "1800"))

_FIELDS = ("id", "username", "password", "is_active", "is_staff", "is_superuser")


def _key(user_id):
    return f"auth-identity:{user_id}"


def remember(user, must_change_password=None):
    """Cache the fields needed to reconstruct this user without the database."""
    try:
        record = {f: getattr(user, f) for f in _FIELDS}
        if must_change_password is not None:
            record["must_change_password"] = bool(must_change_password)
        cache.set(_key(user.pk), record, IDENTITY_TTL_SECONDS)
    except Exception:
        logger.exception("could not cache identity for user_id=%s", getattr(user, "pk", "?"))


def recall(user_id):
    """A User rebuilt from cache, or None.

    The instance is NOT saved and must never be saved — writing it back would
    push a possibly-stale copy over the live row the moment the database
    returns. It exists only to answer "who is this request from".
    """
    try:
        record = cache.get(_key(user_id))
    except Exception:
        return None
    if not record:
        return None
    # EVERY field must be present. `{f: record[f] for f in _FIELDS if f in record}`
    # was the same fail-open shape as the SQL guard's table allowlist (ca69849):
    # a filter applied before a security decision, where ABSENCE silently
    # becomes a permissive default.
    #
    # Django's AbstractUser defaults is_active to TRUE, so a record missing that
    # one key rebuilds a DISABLED account as an ACTIVE one. Measured:
    #
    #     complete record    -> is_active = False
    #     record missing key -> is_active = True
    #
    # remember() always writes all of _FIELDS, so this needs a partial record —
    # a truncated cache entry, or one written by an older deploy before _FIELDS
    # gained a name. Both are ordinary, and neither should be able to reactivate
    # a suspended account.
    #
    # Deny on unknown: an incomplete record is treated as no record at all, so
    # the caller falls back to the database, which is authoritative anyway.
    if not all(f in record for f in _FIELDS):
        missing = sorted(set(_FIELDS) - set(record))
        logger.warning(
            "identity cache record for user_id=%s is missing %s — ignoring it "
            "and falling back to the database",
            user_id, ", ".join(missing),
        )
        return None

    user = User(**{f: record[f] for f in _FIELDS})
    # Django treats a model instance with a pk as persisted; this one is not,
    # and marking it explicitly stops any accidental save() from inserting.
    user._state.adding = False
    user._identity_from_cache = True
    return user


def recall_must_change_password(user_id, default=False):
    """The one profile flag on the permission path, from the same record."""
    try:
        record = cache.get(_key(user_id))
    except Exception:
        return default
    if not record or "must_change_password" not in record:
        return default
    return bool(record["must_change_password"])


def forget(user_id):
    """Drop a cached identity, so a revocation takes effect immediately."""
    try:
        cache.delete(_key(user_id))
    except Exception:
        logger.exception("could not clear cached identity for user_id=%s", user_id)


def is_database_down(exc):
    """Whether an exception means 'the database is unreachable'.

    Deliberately narrow. Only a DatabaseError falls back to the cache — a
    programming error, a missing column or a permission problem must surface as
    an error rather than being papered over with stale identity data.
    """
    return isinstance(exc, DatabaseError)
