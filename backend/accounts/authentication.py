# Copyright (c) 2026 Yash Garad. All rights reserved.

"""CSRF enforcement for endpoints that run BEFORE a session exists.

THE PROBLEM
DRF's @api_view marks every view `csrf_exempt` and delegates the CSRF check to
SessionAuthentication. That works for authenticated endpoints. It leaves a hole
in exactly one place: a view that must run before the user has a session, and so
sets authentication_classes([]).

/api/auth/login/ is that view, and it was unprotected. Verified: a POST with no
CSRF token and `Referer: https://evil.test/` returned HTTP 200 and a valid
session cookie.

WHY THE OBVIOUS FIXES DO NOT WORK
  * @csrf_protect ON the view — receives DRF's Request, not Django's
    HttpRequest, and errors.
  * csrf_protect(view) in urls.py — functools.wraps copies `csrf_exempt = True`
    off the @api_view wrapper onto csrf_protect's own wrapper, so the middleware
    it installs exempts itself. Silently does nothing, which is the worst
    possible outcome for a security control.

WHAT WORKS
An authentication class. DRF calls `authenticate()` on each configured class
before the view body runs; SessionAuthentication already knows how to perform
the CSRF check, so subclassing it and calling that check unconditionally puts
enforcement exactly where DRF expects it. Returning None means "no user
identified", which is correct — this class authenticates nobody, it only
enforces.
"""

from rest_framework.authentication import SessionAuthentication


class CSRFEnforcingAuthentication(SessionAuthentication):
    """Enforces CSRF without authenticating anyone.

    Use on unauthenticated POST endpoints instead of authentication_classes([]),
    which disables the check entirely.
    """

    def authenticate(self, request):
        # Raises rest_framework.exceptions.PermissionDenied (403) when the token
        # is missing, malformed or does not match the cookie.
        self.enforce_csrf(request)
        # No user is established here: login itself decides that from the
        # credentials in the body.
        return None
