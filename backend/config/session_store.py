# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Cache-backed sessions that tell an outage apart from "not signed in".

THE PROBLEM WITH THE STOCK BACKEND
`django.contrib.sessions.backends.cache.SessionStore.load()` is written like
this:

    try:
        session_data = self._cache.get(self.cache_key)
    except Exception:
        # Some backends (e.g. memcache) raise an exception on invalid
        # cache keys. If this happens, reset the session. See #17810.
        session_data = None

Every exception becomes "no session". That is a reasonable default for the case
the comment describes — a malformed key — and it is wrong for a store that is
DOWN. With Redis stopped, a signed-in user's request came back **403**, which
says "you are not permitted", when the truth was "we cannot tell who you are
right now". Measured during resilience testing.

The difference matters to the person receiving it. A 403 tells a student their
account is the problem; they will try their password again, fail, try again, and
eventually contact someone about an account that was never broken. A 503 says
the service is unwell and they should wait — and it is what an uptime monitor
needs to see to alarm on the right thing.

WHAT THIS CHANGES, EXACTLY
Only connection-level failures propagate. Everything else still degrades to an
empty session exactly as Django intends, so a corrupt or malformed key is still
tolerated rather than turned into an outage. The propagated error is caught by
config.middleware.SessionStoreUnavailableMiddleware and rendered as a 503.
"""

from django.contrib.sessions.backends.cache import SessionStore as CacheSessionStore

try:
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
    _OUTAGE_ERRORS = (RedisConnectionError, RedisTimeoutError)
except Exception:  # pragma: no cover - depends on the deployment
    _OUTAGE_ERRORS = ()


class SessionStore(CacheSessionStore):
    """Identical to Django's, except that an unreachable store is not silently
    reinterpreted as an anonymous visitor."""

    def load(self):
        try:
            session_data = self._cache.get(self.cache_key)
        except _OUTAGE_ERRORS:
            # Deliberately NOT swallowed. See the module docstring.
            raise
        except Exception:
            # Django's original behaviour, kept for the case its comment is
            # actually about: a backend rejecting a malformed key.
            session_data = None
        if session_data is not None:
            return session_data
        self._session_key = None
        return {}

    async def aload(self):
        try:
            session_data = await self._cache.aget(await self.acache_key())
        except _OUTAGE_ERRORS:
            raise
        except Exception:
            session_data = None
        if session_data is not None:
            return session_data
        self._session_key = None
        return {}
