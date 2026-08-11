# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Turn a session-store outage into an honest 503 instead of a 500.

WHY THIS EXISTS
Moving sessions to Redis made Redis a hard dependency of signing in, and the
resilience re-test showed what that looked like without this: with Redis
stopped, `POST /api/auth/login/` raised `redis.exceptions.ConnectionError` and
returned **HTTP 500** — in development, as a 240 KB debug traceback.

That is the same defect that was fixed for the Postgres path in
accounts/views.login, reappearing one component to the left. A 500 tells a user
nothing, invites an immediate retry that cannot work, and in production is
indistinguishable from a code bug — so it also misdirects whoever is
investigating.

WHY MIDDLEWARE RATHER THAN A try/except IN THE VIEW
The failure is not confined to the view body. Redis is touched by DRF's
throttle classes (before the view runs), by the session middleware on the way
in and again on the way out, and by the login view itself. Wrapping the view
would leave the throttle and the response-phase session save uncovered, and
those raise just as readily.

WHAT IT DELIBERATELY DOES NOT CATCH
Only Redis connection-level errors. A KeyError, a template error or a database
error must still surface normally — a middleware that swallowed everything into
"try again later" would hide real bugs behind a reassuring message, which is
worse than the 500 it replaced.
"""

import logging

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import JsonResponse

logger = logging.getLogger("django.request")

# Imported defensively: the application must still start if the redis client is
# not installed (for example a deployment that has switched SESSION_ENGINE back
# to the database backend and dropped the dependency).
try:
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - depends on the deployment
    class RedisError(Exception):
        """Placeholder so the isinstance check below is always valid."""


UNAVAILABLE = (
    "Sign-in is temporarily unavailable. Please try again in a few minutes. "
    "This is a problem at our end, not with your account or password."
)


class SessionStoreUnavailableMiddleware:
    """Convert a Redis outage into 503 with a plain sentence."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except RedisError as exc:
            return self._unavailable(request, exc)

    def process_exception(self, request, exception):
        """Covers exceptions raised inside the view.

        Django calls this for view exceptions before they reach __call__, so
        both hooks are needed: this one for the view, __call__ for the
        middleware layers either side of it — notably SessionMiddleware saving
        the session on the way out, which happens after the view has returned.
        """
        if isinstance(exception, RedisError):
            return self._unavailable(request, exception)
        return None

    def _unavailable(self, request, exc):
        logger.error(
            "session store unavailable on %s %s: %s", request.method, request.path, exc
        )
        return JsonResponse({"error": UNAVAILABLE}, status=503)


class ResilientSessionMiddleware(SessionMiddleware):
    """Django's SessionMiddleware, minus the 500 when the store is unreachable.

    WHY THE MIDDLEWARE ABOVE IS NOT SUFFICIENT
    Django wraps EVERY middleware in `convert_exception_to_response`. An
    exception raised inside SessionMiddleware is therefore turned into a 500 by
    the wrapper immediately around it, and never propagates to a middleware
    higher up the stack — so no amount of try/except in
    SessionStoreUnavailableMiddleware can see it.

    That matters because of SESSION_SAVE_EVERY_REQUEST. The idle-timeout design
    re-saves the session on the way OUT of every request, which means a Redis
    outage raises during the RESPONSE phase, after the view has finished. The
    observed effect was precisely that: the request produced a correct 503,
    and then this save failed and replaced it with a 500 carrying a
    ConnectionError traceback.

    Failing to write a session when the store is down loses nothing: there is
    nowhere to write it, the user is being told the service is degraded, and
    the alternative is discarding a good response for a bookkeeping step that
    could not have succeeded either way.
    """

    def process_response(self, request, response):
        try:
            return super().process_response(request, response)
        except RedisError as exc:
            logger.error(
                "could not save the session on %s %s: %s — returning the response "
                "anyway", request.method, request.path, exc,
            )
            return response
