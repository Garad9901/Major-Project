#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
# Backend startup: bring the database to a ready state, then serve.
# Every step here is idempotent, so it is safe to run on every container start.
#
# One entrypoint serves both environments so the startup sequence never drifts
# between them. DJANGO_ENV selects how the app is SERVED, nothing else:
#   development (default) -> manage.py runserver, autoreload, unchanged behaviour
#   production            -> gunicorn, per backend/gunicorn.conf.py
set -e

DJANGO_ENV="${DJANGO_ENV:-development}"

echo "[entrypoint] Environment: ${DJANGO_ENV}"

echo "[entrypoint] Applying database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Configuring read-only database role (rag_agent_ro)..."
python manage.py setup_readonly_role

echo "[entrypoint] Ensuring role groups exist..."
python manage.py setup_roles

echo "[entrypoint] Ensuring bootstrap staff login exists..."
python manage.py create_staff_user

if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  echo "[entrypoint] Seeding demo data (only if the database is empty)..."
  python manage.py seed_demo_data --if-empty
fi

if [ "$DJANGO_ENV" = "production" ]; then
  # WhiteNoise serves from STATIC_ROOT, and the production storage backend
  # (CompressedManifestStaticFilesStorage) requires the manifest this produces.
  # Under `set -e` a failure here stops the container loudly instead of letting
  # gunicorn come up and serve a site with broken assets.
  echo "[entrypoint] Collecting static files..."
  python manage.py collectstatic --noinput --clear

  echo "[entrypoint] Starting gunicorn on port 8000..."
  exec gunicorn config.wsgi:application --config /app/gunicorn.conf.py
fi

echo "[entrypoint] Starting development server on port 8000..."
exec python manage.py runserver 0.0.0.0:8000
