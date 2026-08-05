# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from django.db import connections
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common import ollama
from rag_agent import vector_store

logger = logging.getLogger("health")


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def liveness(request):
    """Cheap liveness probe for the container healthcheck: confirms only that
    the backend process is up and serving. Does NOT check dependencies, so a
    downstream outage (e.g. Ollama) never marks the backend itself unhealthy."""
    return Response({"status": "ok", "service": "backend"})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """Aggregate readiness check across every backing service, for monitoring.
    Returns 200 when all are up, 503 when any is down, plus a per-service
    breakdown so it's obvious which one failed."""
    services = {
        "database": _check_database(),
        "llm": _check_llm(),
        "vector_store": _check_vector_store(),
    }
    all_ok = all(services.values())
    body = {
        "status": "ok" if all_ok else "degraded",
        "services": {name: ("up" if ok else "down") for name, ok in services.items()},
    }
    return Response(body, status=200 if all_ok else 503)


def _check_database():
    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return True
    except Exception as exc:
        logger.warning("health: database check failed: %s", exc)
        return False


def _check_llm():
    return ollama.ping()


def _check_vector_store():
    return vector_store.ping()
