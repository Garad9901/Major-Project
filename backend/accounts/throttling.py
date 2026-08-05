# Copyright (c) 2026 Yash Garad. All rights reserved.

import time

from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


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


class LoginRateThrottle(SimpleRateThrottle):
    """Per-IP rate limit on the login endpoint, counting FAILED attempts only.

    Login is unauthenticated, so a per-user throttle cannot apply — there is no
    user until the attempt succeeds. The client IP is the only identifier
    available, and is what brute-force protection needs anyway.

    WHY THIS COUNTS ONLY FAILURES
    It previously counted EVERY attempt, and that is wrong for this deployment
    in a way that a load test made unmissable: 50 users signing in at once
    produced 40 rejections reading

        "Request was throttled. Expected available in 53 seconds."

    Every student on campus wifi leaves through one NAT gateway, so they all
    share a single public IP and therefore a single bucket. At 10/min the whole
    institute — not each person — got ten sign-ins per minute. A 9am rush would
    have looked exactly like an outage, and the harder people retried the longer
    it would have stayed broken.

    Raising the number does not fix that; it only moves the cliff. The real
    observation is that a SUCCESSFUL login is not evidence of an attack. A
    morning rush is almost entirely successes; credential-stuffing is almost
    entirely failures. Counting only failures separates the two cleanly:
    legitimate users are never throttled no matter how many arrive together,
    while a source guessing passwords still gets ten tries a minute.

    THIS IS NOT THE ONLY BRUTE-FORCE CONTROL, AND IT IS THE WEAKER ONE.
    Per-ACCOUNT lockout (accounts/lockout.py — 5 failures, 15 minutes) is what
    stops one account being ground down, and it is unaffected by any of this.
    This throttle stops ONE SOURCE spraying MANY accounts, which the per-account
    counter cannot see. Neither substitutes for the other.

    IMPORTANT — depends on REST_FRAMEWORK['NUM_PROXIES']. Behind Caddy,
    REMOTE_ADDR is the proxy's container address, identical for every request;
    NUM_PROXIES=1 makes get_ident() read the last X-Forwarded-For hop, which is
    the address Caddy itself appended and therefore cannot be forged by the
    client. See config/settings/base.py.

    CACHE CAVEAT: process-local memory, so accurate only with GUNICORN_WORKERS=1
    — the same caveat as AskRateThrottle above.

    The rate lives in DEFAULT_THROTTLE_RATES['login'].
    """

    scope = "login"

    def get_cache_key(self, request, view):
        # Deliberately a DIFFERENT key namespace from DRF's usual throttle keys:
        # this history holds failures only, not all requests.
        return f"login-failures:{self.get_ident(request)}"

    def allow_request(self, request, view):
        """Check the failure history WITHOUT recording this attempt.

        Recording is done by record_failure() below, called from the view once
        the credentials are known to be wrong. Deliberately does not call
        throttle_success(), which is what would append to the history here.
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()

        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return True

    @classmethod
    def record_failure(cls, request):
        """Charge one failed sign-in against this client address.

        Called from the login view, and ONLY on a failure. Safe to call when
        throttling is disabled (rate is None), in which case it does nothing.
        """
        throttle = cls()
        if throttle.rate is None:
            return
        key = throttle.get_cache_key(request, None)
        now = time.time()
        history = [t for t in cache.get(key, []) if t > now - throttle.duration]
        history.insert(0, now)
        cache.set(key, history, throttle.duration)
