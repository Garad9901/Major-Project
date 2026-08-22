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

# DEMO DATA IS OPT-IN, AND THE DEFAULT CHANGED.
#
# This used to default to true, which was right while this was one deployment
# for one college and wrong the moment it became something a stranger installs.
# A production install must start empty and be populated from the institution's
# own records; seeding invented departments, staff and fees into a real
# deployment would put fabricated data in front of real students.
#
# WHAT THIS ACTUALLY SEEDS, since an earlier version of this comment got it
# wrong: seed_demo_data creates a small invented college — 8 departments,
# 7 faculty, 10 programs, 8 courses, 4 rooms, and the offerings, exams and fee
# rows that hang off them. Low hundreds of rows in total.
#
# It does NOT load the 13,000-row faculty development survey. That is a separate
# manual command (load_faculty_dataset) reading a CSV that is not in this
# repository and must be copied in deliberately — see RUNBOOK.md.
#
# Set SEED_DEMO_DATA=true for an evaluation, a demo or a training environment.
# --if-empty still guards it, so it can never overwrite real data.
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "[entrypoint] SEED_DEMO_DATA=true - seeding demo data (only if the database is empty)..."
  python manage.py seed_demo_data --if-empty
else
  echo "[entrypoint] Demo data disabled (SEED_DEMO_DATA=false). Import your own records - see DATA_IMPORT.md."
fi

# WARM THE EMBEDDING MODEL.
#
# ollama-pull preloads the chat models with `ollama run`, but there is no
# `ollama embed` subcommand and that image ships neither wget nor curl, so the
# embedding model cannot be warmed from there. It is only ~376 MB and loads in
# about a second — but until it is resident, /api/health/ reports "warming" and
# returns 503, so without this a fresh deployment would sit at 503 forever
# waiting for a model nothing had asked for.
#
# Best-effort and non-blocking: a failure here must not stop the backend
# starting. The health endpoint will simply keep reporting "warming", which is
# the truth.
echo "[entrypoint] Warming the embedding model..."
python warm_embedding.py || true

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
