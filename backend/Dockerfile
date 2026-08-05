# Copyright (c) 2026 Yash Garad. All rights reserved.

# Two build targets share one dependency layer so dev and production can never
# drift in their installed packages:
#   development -> source is bind-mounted at runtime, runs as root, autoreloads
#   production  -> source is baked into the image, runs as an unprivileged user
# Compose names the target explicitly in both docker-compose.yml and
# docker-compose.prod.yml, so neither depends on stage ordering.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Upgrade pip itself before installing anything.
#
# pip-audit reported 6 known vulnerabilities in this image, and every one of
# them was in pip 25.0.1 (the version baked into python:3.12-slim) rather than
# in any application dependency — Django, DRF, psycopg2, requests and the rest
# came back clean. Upgrading the installer clears all six.
#
# Pinned rather than bare `--upgrade` so a rebuild is reproducible and a future
# pip release cannot change build behaviour without someone choosing it.
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8000


# --- production ---------------------------------------------------------------
FROM base AS production

# Unprivileged runtime user. A fixed uid/gid keeps file ownership predictable if
# a volume is ever attached.
#
# The home directory IS created, despite nothing in this application writing to
# $HOME. Gunicorn 26's control server opens a socket under $HOME at startup, and
# with no home directory it logged on every single boot:
#
#     [ERROR] Control server error: [Errno 13] Permission denied: '/home/appuser'
#
# Harmless in itself, but an ERROR on every production start is exactly the kind
# of constant noise that trains an operator to ignore the log.
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --create-home appuser

# staticfiles/ is created and owned up front so `collectstatic` (Phase 2) can
# write to it as appuser without making all of /app writable.
RUN mkdir -p /app/staticfiles && chown appuser:appuser /app/staticfiles

COPY --chown=appuser:appuser . .

USER appuser

# entrypoint.sh branches on DJANGO_ENV; docker-compose.prod.yml sets it to
# "production", which selects gunicorn.
CMD ["sh", "entrypoint.sh"]


# --- development --------------------------------------------------------------
# Last stage, so a build with no explicit target still yields the dev image.
FROM base AS development

COPY . .

# entrypoint.sh runs migrations, sets up the read-only DB role, creates the
# staff login, seeds demo data if empty, then starts the server — so the whole
# stack is self-configuring on `docker compose up`.
CMD ["sh", "entrypoint.sh"]
