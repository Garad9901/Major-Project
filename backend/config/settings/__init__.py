# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Settings selector.

This package replaces the former config/settings.py module. Because the package
keeps the same dotted path, DJANGO_SETTINGS_MODULE stays "config.settings" and
manage.py / wsgi.py / asgi.py needed no changes at all.

Selection is driven by DJANGO_ENV, the same variable entrypoint.sh uses to
choose between runserver and gunicorn, so the way the app is served and the way
it is configured can never disagree:

    DJANGO_ENV=production  -> config/settings/production.py   (strict, fails loudly)
    anything else / unset  -> config/settings/development.py  (permissive)

Defaulting to development is the safe direction for this variable: forgetting it
yields a server that is obviously wrong (Vite, DEBUG banner, runserver warning)
rather than one that looks production-ready but is not. Production is opted into
explicitly by docker-compose.prod.yml.
"""

import os

DJANGO_ENV = os.getenv("DJANGO_ENV", "development").strip().lower()

if DJANGO_ENV == "production":
    from .production import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403
