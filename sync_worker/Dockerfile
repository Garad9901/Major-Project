# Copyright (c) 2026 Yash Garad. All rights reserved.

# Mirrors backend/Dockerfile: one dependency layer, two targets.
#   development -> source bind-mounted at runtime, runs as root
#   production  -> source baked in, runs as an unprivileged user

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Both files are copied; only the lock is installed. See backend/Dockerfile
# and the header of requirements.lock for why.
COPY requirements.txt requirements.lock ./
# Upgrade pip itself before installing anything — same fix, same reason, as
# backend/Dockerfile.
#
# That fix was applied to the backend image only, and this image was missed:
# pip-audit against the running sync_worker reported 6 known vulnerabilities,
# all of them in pip 25.0.1 (the version baked into python:3.12-slim) and none
# in an application dependency. The backend, already carrying this line, came
# back clean. Scanning one image of a multi-image stack is how that kind of gap
# survives — audit every image, not just the one serving traffic.
#
# Pinned rather than bare `--upgrade` so a rebuild is reproducible.
# --require-hashes: a substituted artefact fails the build, and a dependency
# added to requirements.txt without regenerating the lock fails it too.
RUN pip install --no-cache-dir --upgrade "pip>=26.1.2" \
    && pip install --no-cache-dir --require-hashes -r requirements.lock


# --- production ---------------------------------------------------------------
FROM base AS production

RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --no-create-home appuser

# The worker persists watermarks and its change queue under /app/data, so that
# directory must be writable by the unprivileged user.
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# .dockerignore excludes test_embedding_pipeline.py from this COPY — that script
# connects as the Postgres OWNER and performs INSERTs, so it must never be
# present in a production image.
COPY --chown=appuser:appuser . .

USER appuser

CMD ["python", "main.py"]


# --- development --------------------------------------------------------------
# Last stage, so a build with no explicit target still yields the dev image.
FROM base AS development

COPY . .

CMD ["python", "main.py"]
