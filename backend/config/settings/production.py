# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Production settings.

DESIGN RULE: this module FAILS LOUDLY rather than falling back. Every value here
that has a safe-but-wrong default in development is required outright, because a
misconfigured production server that boots looks identical to a correct one until
something leaks. A container that refuses to start is a visible, fixable problem;
a container serving with DEBUG=True and ALLOWED_HOSTS=* is an invisible one.

Additional secret-value guards (default passwords, SECRET_KEY length) are added
in Phase 3 and live in accounts/checks.py so they run under `manage.py check`.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import APP_LOGGERS, MIDDLEWARE


def _env_list(name):
    """Comma-separated env var -> list of non-empty, stripped values."""
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


def _require(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} must be set when DJANGO_ENV=production. "
            f"Add it to .env.production (see scripts/generate_secrets.sh)."
        )
    return value


# --- DEBUG: refuse to start if requested ---------------------------------------
# Django would happily run with DEBUG=True here, serving full tracebacks —
# including settings and SQL — to anyone who triggers a 500. Rather than silently
# forcing it off (which would hide an operator's mistaken configuration), this
# treats the combination as a fatal misconfiguration and says so.
if os.getenv("DJANGO_DEBUG", "false").strip().lower() in ("true", "1", "yes", "on"):
    raise ImproperlyConfigured(
        "DJANGO_DEBUG is enabled but DJANGO_ENV=production. Refusing to start. "
        "Debug mode exposes tracebacks, settings and SQL to end users. "
        "Set DJANGO_DEBUG=false in .env.production."
    )

DEBUG = False

# --- secrets: reject example, default and known-burned values ------------------
# Runs before anything else reads a credential, so a server configured from a
# copied .env stops here with a precise list of what to regenerate rather than
# booting with a publicly-known session-signing key. See config/secret_guards.py
# for why this is enforced here rather than only as a system check.
from config.secret_guards import enforce as _enforce_secrets  # noqa: E402

_enforce_secrets()

SECRET_KEY = _require("DJANGO_SECRET_KEY")

# --- host / origin allowlists --------------------------------------------------
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list the exact hostnames/IPs this server is "
        "reached at, e.g. DJANGO_ALLOWED_HOSTS=10.20.30.40,assistant.college.internal"
    )
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS=* disables Django's Host header validation and "
        "permits cache-poisoning and password-reset poisoning via a forged Host "
        "header. List the real hostnames instead."
    )

CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "DJANGO_CSRF_TRUSTED_ORIGINS must be set, e.g. "
        "DJANGO_CSRF_TRUSTED_ORIGINS=https://10.20.30.40 — including the scheme."
    )
for _origin in CSRF_TRUSTED_ORIGINS:
    if not _origin.startswith("https://"):
        raise ImproperlyConfigured(
            f"CSRF trusted origin {_origin!r} is not https://. This deployment "
            "terminates TLS at Caddy and serves nothing over plain HTTP."
        )

# --- CORS ----------------------------------------------------------------------
# The SPA and the API are served from ONE origin behind Caddy, so a browser never
# makes a cross-origin request and this list should normally stay empty.
# CORS_ALLOW_ALL_ORIGINS is not merely unset but explicitly False, so that
# inheriting a True from elsewhere can never happen silently.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = _env_list("DJANGO_CORS_ALLOWED_ORIGINS")

# --- cookies -------------------------------------------------------------------
# Not env-configurable in production: everything is served over HTTPS via Caddy,
# so there is no legitimate reason to emit a non-Secure session cookie.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# --- transport security ---------------------------------------------------------
# Caddy already redirects HTTP->HTTPS at the edge; this is the backstop for any
# request that somehow reaches Django over plain HTTP. Safe because
# SECURE_PROXY_SSL_HEADER (base.py) lets Django recognise proxied HTTPS —
# without that pairing this would cause an infinite redirect loop.
SECURE_SSL_REDIRECT = True

# HSTS DEFAULTS TO OFF, AND YOU SHOULD TURN IT ON — see below for when.
#
# (This comment previously stated as fact that "this server uses a self-signed
# certificate from Caddy's internal CA". That stopped being true when the
# deployment moved to internet-facing: CADDY_TLS defaults to EMPTY, which selects
# a real Let's Encrypt certificate. Left uncorrected it told the operator that
# HSTS was off for a reason that no longer applied, i.e. it argued against ever
# enabling it. The reasoning below is the same; only the trigger has changed.)
#
# HSTS tells a browser "only ever talk to this host over TLS, and DO NOT let the
# user click through a certificate warning." That second half is what makes the
# default-off correct as a STARTING state rather than an end state:
#
#   * With a real Let's Encrypt certificate (CADDY_TLS empty, the default),
#     HSTS is straightforwardly what you want — but only ONCE the certificate is
#     confirmed issued. Enabling it while ACME is still failing, and Caddy is
#     therefore serving its internal-CA fallback, locks every visitor out with no
#     bypass for the full max-age.
#   * With CADDY_TLS="tls internal" (LAN deployments), it stays off until Caddy's
#     root CA is installed on every client machine.
#
# So: confirm the certificate first, then ramp 3600 -> 86400 -> 31536000.
# OPERATIONS.md section 1 has the confirmation command and the same ramp.
#
# SCOPE NOTE — AND THIS SETTING IS INERT IN THE DOCKER DEPLOYMENT.
# An earlier version of this note said the header is emitted by Django, rides on
# /api/ and /static/, and that adding it to Caddyfile.prod was "deliberately NOT
# done". Both halves are false as the stack actually ships. Caddyfile.prod sets
#
#     Strict-Transport-Security "max-age={$CADDY_HSTS_MAX_AGE:0}"
#
# on EVERY response, and a Caddy header directive REPLACES rather than appends,
# so Django's value never reaches a browser — Caddyfile.prod's own comment says
# as much. Left uncorrected, this note sent an operator to the wrong knob: they
# would set DJANGO_HSTS_SECONDS, believe the site was pinned, and in fact still
# be serving max-age=0, which instructs a browser to DISCARD any pin it holds.
# Documented-as-protected while actually unprotected is the worst of the three
# possible states, which is why this is spelled out rather than trimmed.
#
# CADDY_HSTS_MAX_AGE is the knob that reaches the browser; .env.production
# carries both. This setting is kept, and kept in step, so that a deployment
# which ever terminates TLS somewhere other than this Caddyfile is not silently
# left with no HSTS at all.
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = False  # never preload a private/internal hostname

# W021 asks why SECURE_HSTS_PRELOAD is not True. It is False on purpose, one
# line above, and always will be: preload submission is effectively irreversible
# and must never be applied to an institutional hostname. Silenced so that
# `manage.py check --deploy` returns CLEAN once the HSTS ramp above is complete
# - an audit gate that always emits one known warning trains the reader to
# ignore the output, and the next warning to appear would be a real one.
#
# W004 (HSTS not set) is deliberately NOT silenced: while DJANGO_HSTS_SECONDS is
# still 0 that warning is the operator's outstanding to-do, and it disappears by
# itself the moment the ramp is done.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- response headers -----------------------------------------------------------
X_FRAME_OPTIONS = "DENY"           # no framing at all; the SPA never frames itself
SECURE_CONTENT_TYPE_NOSNIFF = True  # no MIME sniffing
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# --- middleware -----------------------------------------------------------------
# Rebuilt rather than appended because ORDER IS SEMANTIC here:
#   SecurityMiddleware must be first  -> it applies the SSL redirect and the
#                                        transport headers above
#   WhiteNoise immediately after it   -> serves static files before any further
#                                        middleware does per-request work
#   XFrameOptions last                -> stamps the header on the way out
#
# These three are absent from the development stack, which is a deliberate
# divergence: runserver serves static itself, and an SSL redirect would fight the
# local workflow. It does mean the middleware chain is not exercised in dev, so
# `manage.py check --deploy` against production settings is the check that
# matters (see the Phase 2 verification notes).
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE,
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- static files ----------------------------------------------------------------
# WhiteNoise serves collected static directly from gunicorn, so no separate
# static server or shared volume is needed. Caddy proxies /static/* here.
#
# CompressedManifestStaticFilesStorage fingerprints filenames and pre-compresses
# them. It REQUIRES `collectstatic` to have run — entrypoint.sh runs it before
# gunicorn starts, under `set -e`, so a failure stops the container loudly rather
# than serving a half-broken site.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- logging -----------------------------------------------------------------------
# JSON lines to stdout. Docker captures stdout, and Phase 5 adds rotation, so the
# application never writes or manages a log file itself.
#
# Level is INFO, not DEBUG: DEBUG-level output from Django and urllib3 includes
# full request bodies and would write student questions — and the records
# returned for them — into the container log at high volume.
_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "config.log_formatters.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        # Unhandled exceptions land here. They MUST reach the operator's logs;
        # what the user sees is a generic message, which is a separate concern
        # handled by DEBUG=False plus the orchestrator's error handling.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Silenced: every SQL statement at DEBUG level, including queries
        # containing student data. Never wanted in production.
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        **{
            name: {"handlers": ["console"], "level": _LOG_LEVEL, "propagate": False}
            for name in APP_LOGGERS
        },
    },
}


# --- database connections ----------------------------------------------------
# Safe to keep connections alive HERE, unlike in development, because gunicorn
# bounds concurrency: GUNICORN_WORKERS(1) x GUNICORN_THREADS(4) = at most 4
# persistent ORM connections, plus the SQL agent's pool (max 8) and the sync
# worker (1). Comfortably inside Postgres's default max_connections of 100.
#
# The development stack uses runserver, which spawns an UNBOUNDED thread per
# request; a 50-user load test there exhausted Postgres outright. See the note
# in base.py.
DATABASES["default"]["CONN_MAX_AGE"] = int(os.getenv("DB_CONN_MAX_AGE", "60"))  # noqa: F405
