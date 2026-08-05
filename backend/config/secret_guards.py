# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Refuses to let production start on example, default or known-burned secrets.

WHY THIS RUNS AT SETTINGS-IMPORT TIME
Django's system-check framework is the tidy place for validation like this, but
it is not sufficient on its own: gunicorn loads config.wsgi directly and does
NOT run system checks. A check-only guard would therefore be silently skipped by
the very process that serves production traffic. So the authoritative call is
made from settings/production.py at import time, which every process performs.
The same logic is additionally exposed as a system check (see `register_checks`)
so `manage.py check` reports it in the normal way, which the Phase 7
verification script relies on.

WHY SOME VALUES ARE MATCHED BY HASH
Known-bad values fall into two kinds:

  * Published placeholders (`postgres`, `staffpass123`, ...). These already
    appear in .env.example in this repository, so naming them again here reveals
    nothing new and keeps the code readable.

  * Credentials that were genuinely configured at some point — specifically the
    rag_agent_ro password that was previously hard-coded in
    db/sql/create_rag_agent_ro.sql. Writing that back into the repository as a
    literal would re-introduce the exact exposure that was cleaned up. It is
    matched by SHA-256 instead: the guard can still recognise it, but the value
    is not recoverable from this file.

A hash is not a secret. The reverse is not true, which is the whole point.
"""

import hashlib
import os

# Minimum length for Django's SECRET_KEY. Django's own generator produces 50
# characters; anything shorter has been shortened by hand and is suspect.
MIN_SECRET_KEY_LENGTH = 50

# Placeholder values shipped in .env.example. Present in the repository already.
_KNOWN_DEFAULT_LITERALS = {
    "DJANGO_SECRET_KEY": {
        "dev-insecure-secret-key-change-me",
        "change-me",
        "secret",
    },
    "POSTGRES_PASSWORD": {
        "postgres",
        "password",
        "changeme",
    },
    "STAFF_PASSWORD": {
        "staffpass123",
        "password",
        "admin",
    },
    "RAG_AGENT_RO_PASSWORD": {
        "CHANGE_ME_STRONG_PASSWORD",
        "rag_agent_ro",
    },
}

# SHA-256 of values that must never reach production but must not be written
# here in the clear. See the module docstring.
_KNOWN_DEFAULT_HASHES = {
    "RAG_AGENT_RO_PASSWORD": {
        # The password formerly hard-coded in db/sql/create_rag_agent_ro.sql.
        # Burned by that exposure; must not be reused on a production server.
        "f1a55487954cc3d21e9f9785bc6b45ead01225b5f08dd9292861f483c2826252",
    },
}

# Every secret production requires. Absence is as fatal as a default value.
_REQUIRED = [
    "DJANGO_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "STAFF_PASSWORD",
    "RAG_AGENT_RO_PASSWORD",
]


def _is_known_default(name, value):
    if value in _KNOWN_DEFAULT_LITERALS.get(name, ()):
        return True
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest in _KNOWN_DEFAULT_HASHES.get(name, ())


def find_secret_problems(env=None):
    """Return a list of human-readable problems. Empty list means all clear.

    Never includes a secret value in its output — only the variable's NAME and
    what is wrong with it. These strings end up in container logs, which are
    read by operators and may be pasted into a support channel.
    """
    env = os.environ if env is None else env
    problems = []

    for name in _REQUIRED:
        value = (env.get(name) or "").strip()

        if not value:
            problems.append(f"{name} is not set.")
            continue

        if _is_known_default(name, value):
            problems.append(
                f"{name} is still set to a known example/default value. "
                f"Generate a fresh one with scripts/generate_secrets.sh."
            )
            continue

        if name == "DJANGO_SECRET_KEY" and len(value) < MIN_SECRET_KEY_LENGTH:
            problems.append(
                f"DJANGO_SECRET_KEY is {len(value)} characters; "
                f"at least {MIN_SECRET_KEY_LENGTH} are required. It signs session "
                f"cookies, so a short key means forgeable logins."
            )

    return problems


def enforce():
    """Raise ImproperlyConfigured if any secret is missing, default or too short.

    Called from settings/production.py. Imported lazily inside the function to
    avoid a circular import during Django's settings bootstrap.
    """
    problems = find_secret_problems()
    if not problems:
        return

    from django.core.exceptions import ImproperlyConfigured

    bullets = "\n".join(f"  - {p}" for p in problems)
    raise ImproperlyConfigured(
        "Refusing to start in production with insecure secrets.\n"
        f"{bullets}\n"
        "Run scripts/generate_secrets.sh to produce a fresh .env.production."
    )


def register_checks():
    """Expose the same validation through `manage.py check`.

    Registered from accounts.apps so it participates in the normal check run.
    Advisory only in development; production has already refused to import.
    """
    from django.core.checks import Error, register

    @register("security")
    def _secret_check(app_configs, **kwargs):
        if os.getenv("DJANGO_ENV", "development").strip().lower() != "production":
            return []
        return [
            Error(problem, id=f"secrets.E{i:03d}")
            for i, problem in enumerate(find_secret_problems(), start=1)
        ]
