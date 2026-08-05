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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


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
