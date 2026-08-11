# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Forcibly signing one user out of everywhere — with cache-backed sessions.

WHY THIS FILE HAD TO EXIST
Session revocation used to be a table scan:

    for session in Session.objects.filter(expire_date__gte=now):
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()

That works only because every session is a row. Once sessions moved to Redis
(see SESSION_ENGINE in config/settings/base.py) `django_session` is empty, so
the loop finds nothing and silently revokes NOTHING — the worst possible
outcome for an incident-response tool, because it reports success. There is no
equivalent query for a cache: session keys are random and the store is not
indexed by user.

TWO INDEPENDENT MECHANISMS, ON PURPOSE
Revocation is what you reach for when an account is compromised, so it must not
have a single point of failure of its own.

  1. THE INDEX BELOW. On login, the user's session key is added to a per-user
     set in the cache. Revoking reads that set and deletes each session through
     the configured session backend. Precise, immediate, and works whichever
     backend is configured.

  2. DJANGO'S AUTH HASH, which needs no index at all and cannot be defeated by
     one being lost. Every session stores a hash derived from the user's
     password; `django.contrib.auth.get_user` compares it on each request and
     rejects the session if it no longer matches. So CHANGING THE PASSWORD
     invalidates every existing session on its own, and deactivating the user
     does the same via `user_can_authenticate`. Both of the management commands
     that call revoke_all() also do one of those things, which means revocation
     still holds even if the index were somehow empty.

Mechanism 2 is the guarantee. Mechanism 1 makes it immediate and explicit, and
covers the case where you want to end sessions WITHOUT changing the password.

WHY THE INDEX CAN BE STALE WITHOUT BEING WRONG
Entries are added on login and expire with the same TTL as the session, but a
session that ends by logout or timeout leaves its key in the set until the set
itself expires. Revoking then deletes keys that are already gone, which is a
no-op. The index is therefore allowed to over-list and never to under-list, and
the count returned by revoke_all() is of sessions that actually existed.
"""

import logging
from importlib import import_module

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import caches
from django.dispatch import receiver

logger = logging.getLogger("accounts")

# One extra hour beyond the session lifetime, so the index cannot expire before
# the sessions it points at — which would leave a live session unrevokable.
_INDEX_TTL_SECONDS = int(getattr(settings, "SESSION_COOKIE_AGE", 1800)) + 3600


def _cache():
    return caches[getattr(settings, "SESSION_CACHE_ALIAS", "default")]


def _index_key(user_id):
    return f"user-sessions:{user_id}"


def _session_store():
    """The SessionStore class for whatever backend is configured.

    Resolved from settings rather than imported directly so this module keeps
    working if SESSION_ENGINE is changed back to the database backend — which
    is a supported fallback, not a hypothetical.
    """
    return import_module(settings.SESSION_ENGINE).SessionStore


def remember(user_id, session_key):
    """Record that `session_key` belongs to `user_id`.

    Best-effort: a failure here must never block a login. The cost of losing an
    index entry is that revocation falls back to mechanism 2 (see the module
    docstring), not that anything breaks.
    """
    if not session_key:
        return
    try:
        cache = _cache()
        key = _index_key(user_id)
        keys = set(cache.get(key) or [])
        keys.add(session_key)
        cache.set(key, list(keys), _INDEX_TTL_SECONDS)
    except Exception:
        logger.exception("could not index session for user_id=%s", user_id)


@receiver(user_logged_in)
def _index_on_login(sender, request, user, **kwargs):
    """Index the session key AFTER login.

    Must be after: django_login() calls cycle_key(), which discards the
    pre-login session key and issues a new one. Indexing before would store a
    key that no longer exists, and the real session would be unrevokable.
    `user_logged_in` fires at the end of login(), so the key here is the final
    one.
    """
    session = getattr(request, "session", None)
    if session is None:
        return
    if session.session_key is None:
        # Nothing has forced the key to be created yet. Do it now, otherwise
        # there is nothing to index.
        session.save()
    remember(user.pk, session.session_key)


def revoke_all(user):
    """End every session belonging to `user`. Returns how many were destroyed.

    Used by disable_user and reset_password, and safe to call directly during an
    incident. Never raises: an operator running this at 3am needs it to do as
    much as it can and say what it did, not to abort halfway.
    """
    destroyed = 0
    Store = _session_store()

    # --- indexed sessions (the cache backend) --------------------------------
    try:
        cache = _cache()
        key = _index_key(user.pk)
        for session_key in list(cache.get(key) or []):
            try:
                store = Store(session_key=session_key)
                # exists() distinguishes "was live and is now gone" from "was
                # already expired", so the returned count is truthful.
                if store.exists(session_key):
                    store.delete()
                    destroyed += 1
            except Exception:
                logger.exception("could not delete session %s", session_key[:8])
        cache.delete(key)
    except Exception:
        logger.exception("could not read the session index for %r", user.username)

    # --- database rows -------------------------------------------------------
    # Still swept, for two reasons: sessions created before the switch to Redis
    # are still rows, and SESSION_ENGINE can legitimately be set back to the
    # database backend. Skipped without complaint if Postgres is unreachable,
    # since the point of the change was to stop that blocking anything.
    try:
        from django.contrib.sessions.models import Session
        from django.utils import timezone

        for row in Session.objects.filter(expire_date__gte=timezone.now()):
            if row.get_decoded().get("_auth_user_id") == str(user.pk):
                row.delete()
                destroyed += 1
    except Exception as exc:
        logger.warning("could not sweep database sessions for %r: %s", user.username, exc)

    # Drop the cached identity too. Without this, a user disabled while the
    # database is healthy could still be reconstructed from cache if the
    # database went down within the TTL — revocation must not have a window.
    from . import identity
    identity.forget(user.pk)

    logger.warning(
        "SESSIONS REVOKED username=%r count=%d", user.username, destroyed
    )
    return destroyed
