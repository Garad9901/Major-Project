# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Settings shared by every environment.

Nothing environment-specific belongs here. In particular this module does NOT
set SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, CORS, cookie
security flags or logging — each of those is a security decision whose safe
value differs between development and production, and defining a permissive
default here would mean production silently inherits it if the production module
ever forgets to override. They are set in development.py / production.py.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# settings/base.py -> settings/ -> config/ -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# The public host/IP the assistant is reached at (behind the HTTPS proxy).
SERVER_HOST = os.getenv("SERVER_HOST", "localhost")

# --- HTTPS awareness ----------------------------------------------------------
# The stack always sits behind the Caddy reverse proxy, which terminates TLS and
# forwards X-Forwarded-Proto. Without this Django believes every request is
# plain HTTP and will refuse to set Secure cookies, so it belongs in base rather
# than only in production.
#
# SAFE ONLY because nothing but Caddy can reach gunicorn: the backend port is
# published on 127.0.0.1 only and the container is on an internal bridge network.
# If the backend were ever exposed directly, a client could forge this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_HTTPONLY = True  # session cookie is never readable by JavaScript
SESSION_COOKIE_SAMESITE = "Lax"

# --- session timeout ----------------------------------------------------------
# Log a user out after this long with NO activity. 30 minutes by default.
#
# These two settings only do the right thing TOGETHER, and either alone is a
# trap:
#
#   SESSION_COOKIE_AGE alone           -> a HARD cap. The user is thrown out
#                                         30 minutes after LOGGING IN even if
#                                         they are actively using the system,
#                                         which on a stack where one answer can
#                                         take two minutes is a real risk of
#                                         losing work mid-question.
#   SESSION_SAVE_EVERY_REQUEST = True  -> re-stamps the expiry on every request,
#                                         turning the hard cap into an IDLE
#                                         timeout. This is what was asked for.
#
# The cost is a session-table write per request. At 50 users that is nothing;
# it is worth knowing about before scaling further.
SESSION_COOKIE_AGE = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))  # 30 min
SESSION_SAVE_EVERY_REQUEST = True

# Close the session when the browser closes, in addition to the idle timeout.
# Shared and lab machines are normal in a college.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SAMESITE = "Lax"

# CSRF_COOKIE_HTTPONLY is deliberately left at its default of False. The SPA
# reads the csrftoken cookie from JavaScript to echo it back as the X-CSRFToken
# header; setting it True would break every POST in the application. This is the
# documented Django pattern for SPA clients and is not a weakness on its own —
# the token is not a credential, and the session cookie remains httpOnly.

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "accounts",
    "health",
    "academics",
    "sql_agent",
    "rag_agent",
    "router_agent",
    "synthesis_agent",
    "verification_agent",
    "web_agent",
    "orchestrator",
    "experiments",
    "audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "college_rag"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.getenv("POSTGRES_HOST", "postgres"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        # Reuse the app-owner connection across requests instead of opening and
        # closing one every time. Django's default is 0 — a fresh connect and
        # disconnect per request.
        #
        # This is the ORM connection (audit rows, conversation history, sessions,
        # auth), which is touched on EVERY request including cache hits. The
        # SQL agent's read-only connection is pooled separately and for a
        # different reason — see sql_agent/db.py.
        #
        # DEFAULTS TO 0 (close after each request). Persistent connections are
        # only safe when the number of concurrent workers is BOUNDED.
        #
        # This was set to 60 and it caused an outage under load, caught by the
        # 50-user load test:
        #
        #     psycopg2.OperationalError: FATAL: sorry, too many clients already
        #
        # Django keeps one connection PER THREAD. `runserver` spawns an
        # unbounded thread per request, so 50 concurrent users held 50+
        # connections open for 60s each and exhausted Postgres's
        # max_connections (default 100) — taking down login for everyone,
        # including users who would have hit the cache.
        #
        # Production is different and safe: gunicorn runs 1 worker x 4 threads,
        # so at most 4 connections are ever held. config/settings/production.py
        # therefore raises this deliberately. Do not raise it here without also
        # bounding the thread count.
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
        # Django 4.1+: drops a connection that has gone bad rather than raising
        # on the next query. Without this, reusing connections turns a transient
        # network blip into an error for the next request that borrows it.
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            # TLS to the database, on the internal network too. "require"
            # encrypts the link but does not verify the server certificate —
            # see docker/Dockerfile.postgres for the reasoning and the limits.
            "sslmode": os.getenv("POSTGRES_SSLMODE", "require"),
        },
    }
}

# Applied by the change-password endpoint and by the account-creation commands.
# Enforced in development too: a rule that only exists in production is one that
# gets discovered at the worst possible moment.
AUTH_PASSWORD_VALIDATORS = [
    {
        # 12 rather than Django's default 8. These accounts sit in front of a
        # database of student records on a network where an attacker can retry
        # indefinitely against the login endpoint.
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        # Rejects the ~20,000 most common passwords. The single highest-value
        # validator here: real-world compromises are overwhelmingly guessed
        # passwords, not cracked ones.
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        # Rejects passwords too similar to the username/name/email. Matters
        # especially for bulk-provisioned student accounts, where the username
        # is a predictable roll number.
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- static files -------------------------------------------------------------
# STATIC_ROOT is where `collectstatic` writes. It is set in base (not just
# production) so that running collectstatic locally behaves identically to
# running it in the production image.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # JSON only. The browsable API is deliberately absent: it renders HTML with
    # user-supplied data and exposes a writable form UI, neither of which has any
    # place on a server holding student records.
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Session-cookie auth (httpOnly, CSRF-protected) rather than a token the
    # browser stores in localStorage where injected JS could read it.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Everything requires an authenticated session unless it explicitly opts
    # out (login/csrf). /api/ask/ further narrows this to staff.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Per authenticated user. Genuinely per-person since Phase 4 — see the
        # note in accounts/throttling.AskRateThrottle about what this does and
        # does not protect.
        "ask": os.getenv("ASK_RATE_LIMIT", "10/min"),
        # Per client IP on the login endpoint only. 10/min allows a person to
        # mistype a few times, while making online password guessing useless:
        # even 10 attempts a minute is ~5,000 a year against one account.
        "login": os.getenv("LOGIN_RATE_LIMIT", "10/min"),
    },
    # CRITICAL BEHIND A PROXY. Every request reaches Django from Caddy, so
    # REMOTE_ADDR is always the proxy's container IP. Without this, DRF's
    # per-IP throttle would treat the entire institute as ONE client: a single
    # user mistyping their password would lock out everybody, and the login
    # rate limit would be worthless. NUM_PROXIES=1 tells DRF to take the client
    # address from X-Forwarded-For instead.
    #
    # Trustworthy only because nothing but Caddy can reach gunicorn (the backend
    # port is published on 127.0.0.1 and the network is an internal bridge). If
    # the backend were exposed directly, clients could forge this header.
    "NUM_PROXIES": 1,
}

# --- audit log retention --------------------------------------------------------
# The audit log records the question text, username, client IP and timestamp for
# every request. Against a database of real student records that is personal
# data, so it is kept for a bounded period and then purged — see
# audit/management/commands/purge_audit_log.py, and the retention discussion in
# DEPLOYMENT.md.
AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))

# Backing-service URLs. Carried over from the pre-split settings module for
# parity. Note that the agent code reads these from the environment directly
# (common/ollama.py, rag_agent/vector_store.py) rather than through
# django.conf.settings, so these are currently unreferenced — kept so that
# anything added later can rely on them being present.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

# Loggers whose output matters operationally. The handler and level attached to
# them differ per environment, so the list lives here and the wiring lives in
# development.py / production.py.
APP_LOGGERS = [
    "sql_agent",
    "rag_agent",
    "router_agent",
    "synthesis_agent",
    "verification_agent",
    "orchestrator",
    "health",
    "accounts",
    "audit",
]
