# Copyright (c) 2026 Yash Garad. All rights reserved.

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AskRateThrottle(UserRateThrottle):
    """Per-user rate limit for the assistant endpoint.

    Each /api/ask/ call fans out into several CPU-bound local-LLM calls, so an
    unthrottled user (or a hijacked session) could saturate the server and deny
    service to everyone else. The rate lives in
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['ask'].

    PHASE 4 RE-CHECK — this limit is only now doing what its name says. Until
    per-user accounts existed, every request came from the single shared `staff`
    login, so UserRateThrottle keyed them all into ONE bucket: the whole
    institute shared 10 requests/minute between them, and one busy user starved
    everyone. With per-user accounts each person gets their own bucket, so 10/min
    is now a genuine per-person limit.

    That makes the AGGREGATE load the thing to watch instead: 200 students at
    10/min each is 2,000 requests/minute arriving at a server that can serve
    roughly 3 per minute. The rate limit does not protect the LLM from that —
    it is not a queue. Phase 5 adds the concurrency limiter that does.

    CACHE CAVEAT: this uses Django's cache, which defaults to per-process local
    memory, so the counter lives inside ONE gunicorn worker.

    That is correct today only because production runs exactly ONE worker.
    (An earlier version of this note said three, which was true of the value
    scripts/generate_secrets.sh used to write; that has since been corrected to
    one precisely because process-local state like this counter — and the LLM
    semaphore in orchestrator/concurrency.py — is only accurate with a single
    worker.)

    So: raising GUNICORN_WORKERS to N silently multiplies this limit by N,
    without any error or warning. Do not raise it without first moving this
    counter to a shared cache (Redis/Memcached).
    """

    scope = "ask"


class LoginRateThrottle(AnonRateThrottle):
    """Per-IP rate limit on the login endpoint.

    Login is unauthenticated, so a per-user throttle cannot apply — there is no
    user until the attempt succeeds. AnonRateThrottle keys on client IP, which
    is the only identifier available and is what brute-force protection needs
    anyway.

    IMPORTANT — this depends on REST_FRAMEWORK['NUM_PROXIES'] being set. Behind
    Caddy, REMOTE_ADDR is the proxy's container address, identical for every
    request. Without NUM_PROXIES, DRF would key every login attempt in the
    institute into a single bucket: one user fat-fingering their password would
    lock out everybody, and an attacker would get the whole institute's budget.
    NUM_PROXIES=1 makes DRF read the client address from X-Forwarded-For
    instead. See config/settings/base.py.

    The rate lives in DEFAULT_THROTTLE_RATES['login'].
    """

    scope = "login"
