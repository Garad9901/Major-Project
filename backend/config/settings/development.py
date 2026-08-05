# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Development settings — permissive by design, never for a real server.

This module reproduces the behaviour the project had before the settings split,
so the local workflow is unchanged. Every relaxation here is one that
production.py explicitly reverses.
"""

import os

from .base import *  # noqa: F401,F403
from .base import APP_LOGGERS, SERVER_HOST

# Insecure by design: this key is public in .env.example. production.py refuses
# to start if this value is still in use.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

# Cookies are marked Secure (HTTPS-only) by default even in development, because
# the dev stack also runs behind Caddy over HTTPS. Set COOKIE_SECURE=false only
# if deliberately running without the proxy.
_cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SESSION_COOKIE_SECURE = _cookie_secure
CSRF_COOKIE_SECURE = _cookie_secure

CSRF_TRUSTED_ORIGINS = [
    f"https://{SERVER_HOST}",
    "https://localhost",
]

# Wide open so a Vite dev server on any port can call the API from the browser.
# production.py sets this to False and uses an explicit allowlist.
CORS_ALLOW_ALL_ORIGINS = True

# --- logging ------------------------------------------------------------------
# Human-readable lines, DEBUG-level detail, everything to the console.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname:8} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        name: {"handlers": ["console"], "level": "INFO", "propagate": False}
        for name in APP_LOGGERS
    },
}
