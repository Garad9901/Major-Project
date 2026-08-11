# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import identity, lockout
from .authentication import CSRFEnforcingAuthentication
from .models import UserProfile, profile_for
from .throttling import LoginRateThrottle

logger = logging.getLogger("accounts")


def _client_ip(request):
    # Used only for log lines here (failed logins, lockouts), not for any
    # security decision — the per-IP throttle keys off DRF's own get_ident(),
    # which reads the LAST hop via NUM_PROXIES=1.
    #
    # Trusting hop [0] is safe only because Caddy replaces a client-supplied
    # X-Forwarded-For rather than appending to it. See the fuller note on the
    # identical function in orchestrator/views.py before changing the proxy.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_payload(user):
    """The signed-in user, as the SPA needs it.

    TOLERATES A DATABASE OUTAGE, because /api/auth/me/ is the first call the SPA
    makes on load. If it 500s, the app cannot paint at all — so a user who is
    still perfectly able to receive degraded answers sees a broken page instead
    of a working one, which would waste most of the benefit of keeping sessions
    in Redis.

    `role` and `theme` come from the profile row and are simply unavailable
    while Postgres is down; the fallbacks are the least surprising values and
    are cosmetic. `must_change_password` is NOT cosmetic — it gates access — so
    it comes from the cached identity written on the last healthy request
    rather than being defaulted here.
    """
    try:
        profile = profile_for(user)
    except DatabaseError:
        logger.warning(
            "serving /me/ for %r from cached identity — database unavailable",
            user.username,
        )
        return {
            "username": user.username,
            "role": "student",
            "is_staff": user.is_staff,
            "must_change_password": identity.recall_must_change_password(user.pk),
            "theme": "system",
            # Lets the SPA say so, rather than silently showing stale details.
            "degraded": True,
        }
    return {
        "username": user.username,
        "role": profile.role,
        "is_staff": user.is_staff,
        "must_change_password": profile.must_change_password,
        # Returned on login and on /me/ so the SPA can paint the correct theme
        # on first render, instead of flashing the wrong one then correcting it.
        "theme": profile.theme,
    }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf(request):
    # Force CsrfViewMiddleware to set the csrftoken cookie so the SPA can read
    # it and send it back as the X-CSRFToken header on POSTs.
    get_token(request._request)
    return Response({"detail": "CSRF cookie set."})


@api_view(["POST"])
# CSRF IS ENFORCED HERE, EXPLICITLY. Do not remove this decorator.
#
# DRF's @api_view marks every view csrf_exempt and then relies on
# SessionAuthentication to re-apply the check. This view sets
# authentication_classes([]) — because login must work before a session exists —
# which meant NOTHING enforced CSRF on it. Verified exploitable: a POST with no
# CSRF token and Referer: https://evil.test/ returned HTTP 200 and a valid
# session cookie.
#
# That is login CSRF. An attacker cannot read anything with it directly, but
# they can silently sign a victim's browser into the ATTACKER'S account; the
# victim then asks questions believing the session is theirs, and every question
# and answer is written to the attacker's conversation history for them to read
# later. On a system answering questions about student records that is a
# confidentiality breach, not a nuisance.
#
# The fix is CSRFEnforcingAuthentication (see accounts/authentication.py for why
# the two obvious alternatives — @csrf_protect on the view, and csrf_protect() in
# urls.py — both fail, the second SILENTLY). It authenticates nobody; it only
# runs DRF's CSRF check before the view body.
@authentication_classes([CSRFEnforcingAuthentication])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])  # per-IP brute-force protection
def login(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    client_ip = _client_ip(request)

    # Resolve the profile WITHOUT revealing whether the account exists. Used
    # only to count failures and check the lock; every response below is the
    # same regardless of what is found here.
    from django.contrib.auth.models import User
    try:
        existing = User.objects.filter(username=username).first()
        profile = profile_for(existing) if existing else None
        locked = bool(profile and lockout.is_locked(profile))

        user = authenticate(request, username=username, password=password)
    except DatabaseError as exc:
        # SIGNING IN STILL NEEDS POSTGRES, AND ALWAYS WILL.
        #
        # Sessions moved to Redis so that an already-signed-in user survives a
        # database outage (see SESSION_ENGINE in settings/base.py). Verifying a
        # password cannot move with them: the user row and the password hash
        # live in Postgres, and checking a credential against a store you
        # cannot read is not something to work around.
        #
        # So this path is expected to fail during a database outage. What is
        # NOT acceptable is HOW it used to fail — an unhandled OperationalError
        # became a 500, which in development rendered a 198 KB debug traceback
        # and in production is an opaque server error that tells the user
        # nothing and invites them to retry immediately.
        #
        # 503 with a plain sentence is the honest answer: this is temporary,
        # it is our end, and there is nothing for the user to fix.
        logger.error("login unavailable: database error for username=%r: %s", username, exc)
        return Response(
            {"error": "Sign-in is temporarily unavailable while the college "
                      "records system is being restored. Please try again in a "
                      "few minutes. Anyone already signed in can continue."},
            status=503,
        )

    if locked:
        # Password checked FIRST so the lock is only disclosed to someone who
        # already knows the password. A guesser gets the ordinary rejection and
        # cannot use the lock as an account-exists oracle. See accounts/lockout.py.
        if user is not None:
            mins = max(1, round(lockout.seconds_remaining(profile) / 60))
            logger.warning(
                "login refused: account locked username=%r ip=%s", username, client_ip
            )
            return Response(
                {"error": f"This account is temporarily locked after repeated "
                          f"failed sign-in attempts. Try again in {mins} minute(s), "
                          f"or ask an administrator to reset it."},
                status=423,  # Locked
            )
        # Wrong password against a locked account: still a failed attempt, so it
        # still counts towards the per-IP budget. See LoginRateThrottle.
        LoginRateThrottle.record_failure(request)
        return Response({"error": "Invalid username or password."}, status=401)

    if user is None:
        # Logged so repeated failures against one account or from one address
        # are visible. The attempted password is deliberately never recorded.
        logger.warning("failed login attempt username=%r ip=%s", username[:150], client_ip)
        # TWO SEPARATE COUNTERS, deliberately, and both are charged here:
        #   per-IP      caps one SOURCE spraying many accounts (this throttle)
        #   per-ACCOUNT caps one ACCOUNT being ground down from anywhere (below)
        # The per-IP one is charged for unknown usernames too — an attacker
        # guessing usernames must not get a free budget by guessing wrong ones.
        LoginRateThrottle.record_failure(request)
        if profile is not None:
            lockout.record_failure(profile, username, client_ip)
        # Deliberately identical response for "no such user", "wrong password",
        # "account disabled" and "just got locked" — distinguishing them would
        # let an attacker enumerate valid usernames.
        return Response({"error": "Invalid username or password."}, status=401)

    lockout.record_success(profile)

    # The is_staff gate that used to be here has been REMOVED. Students hold
    # non-staff accounts and are legitimate users of the assistant; authorisation
    # is now decided per-endpoint (see accounts/permissions.CanUseAssistant).

    django_login(request, user)
    logger.info("login username=%r ip=%s", user.username, _client_ip(request))
    return Response(_user_payload(user))


@api_view(["POST"])
def logout(request):
    django_logout(request)  # flushes the session
    return Response({"detail": "Logged out."})


@api_view(["GET"])
def me(request):
    # Requires an authenticated session (returns 403 otherwise), so the SPA
    # can ask "am I logged in, and must I change my password?" on load.
    return Response(_user_payload(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change the current user's password and clear must_change_password.

    Gated on IsAuthenticated rather than CanUseAssistant on purpose: a user who
    must change their password cannot pass CanUseAssistant, so requiring it here
    would make the flag impossible to clear.
    """
    current = request.data.get("current_password") or ""
    new = request.data.get("new_password") or ""

    if not request.user.check_password(current):
        logger.warning(
            "failed password change (wrong current password) username=%r ip=%s",
            request.user.username, _client_ip(request),
        )
        return Response({"error": "Your current password is incorrect."}, status=400)

    if new == current:
        return Response(
            {"error": "Your new password must be different from your current one."},
            status=400,
        )

    # Applies AUTH_PASSWORD_VALIDATORS. Passing `user` enables the similarity
    # validator to compare against the username and other personal fields.
    try:
        validate_password(new, user=request.user)
    except ValidationError as exc:
        return Response({"error": " ".join(exc.messages)}, status=400)

    request.user.set_password(new)
    request.user.save(update_fields=["password"])

    profile = profile_for(request.user)
    profile.must_change_password = False
    profile.password_changed_at = timezone.now()
    profile.save(update_fields=["must_change_password", "password_changed_at"])

    # Changing a password rotates the session auth hash, which would log the
    # user out of the session they are currently using. This keeps them signed
    # in while still invalidating any OTHER session for this account.
    update_session_auth_hash(request, request.user)

    logger.info(
        "password changed username=%r ip=%s", request.user.username, _client_ip(request)
    )
    return Response({"detail": "Password changed.", **_user_payload(request.user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_preferences(request):
    """Persist UI preferences on the user's profile.

    Server-side rather than localStorage so the choice follows the account
    across browsers and machines, and survives clearing site data.

    Gated on IsAuthenticated, not CanUseAssistant: someone who still has to
    change their initial password should not be stuck with the wrong theme
    while they do it.
    """
    theme = (request.data.get("theme") or "").strip().lower()
    valid = {choice for choice, _ in UserProfile.THEME_CHOICES}
    if theme not in valid:
        return Response(
            {"error": f"theme must be one of: {', '.join(sorted(valid))}"}, status=400
        )

    profile = profile_for(request.user)
    profile.theme = theme
    profile.save(update_fields=["theme"])
    return Response({"theme": profile.theme})
