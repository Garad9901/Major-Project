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
        # Sessions and the login lockout live here. Reported separately from
        # the database because the two outages look nothing alike to a user:
        # Postgres down degrades answers, Redis down signs everybody out.
        "sessions": _check_sessions(),
        "vector_store": _check_vector_store(),
    }

    # THE LANGUAGE MODEL HAS THREE STATES, NOT TWO, AND CONFLATING TWO OF THEM
    # MADE THIS ENDPOINT LIE ON EVERY FRESH DEPLOYMENT.
    #
    # This used to be `ollama.ping()`, which GETs /api/tags — a list of the
    # models on DISK. It returns 200 as soon as the server is listening, whether
    # or not anything is loaded into memory. Demonstrated by unloading all three
    # models and re-querying: this endpoint still answered
    # {"status":"ok","llm":"up"} with HTTP 200 while every question would have
    # cold-loaded and timed out.
    #
    # That is the first thing a buyer meets. Loading the models takes ~15
    # minutes on the reference hardware, and for all of it the monitoring said
    # "ok" while the product did not work.
    #
    #   down     Ollama unreachable
    #   warming  reachable, model not resident — the next question WILL time out
    #   up       resident; a question can be served now
    llm_ready, llm_detail = ollama.is_ready()
    llm_reachable = ollama.ping()
    if llm_ready:
        llm_state = "up"
    elif llm_reachable:
        llm_state = "warming"
    else:
        llm_state = "down"

    states = {name: ("up" if ok else "down") for name, ok in services.items()}
    states["llm"] = llm_state

    # WARMING IS NOT READY. This endpoint is what a load balancer and an uptime
    # monitor consult before sending traffic, so it must return 503 until a
    # question can actually be answered. Reporting 200 while warming is how a
    # deployment gets declared live 15 minutes before it works.
    all_ok = all(services.values()) and llm_ready
    body = {
        "status": "ok" if all_ok else ("warming" if llm_state == "warming"
                                       and all(services.values()) else "degraded"),
        "services": states,
    }
    if llm_state != "up":
        body["llm_detail"] = llm_detail
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


def _check_sessions():
    """Round-trips a value rather than pinging: a Redis at its memory ceiling
    accepts connections and refuses writes, which a ping would call healthy
    while no new session could be stored. See status_view._redis."""
    try:
        from django.core.cache import cache

        cache.set("health-probe", "ok", 10)
        return cache.get("health-probe") == "ok"
    except Exception as exc:
        logger.warning("health: session store check failed: %s", exc)
        return False


def _check_llm():
    """Liveness only — kept for callers that genuinely want "is the server
    there". The aggregate check above deliberately does NOT use this; see the
    comment there for what it failed to distinguish."""
    return ollama.ping()


def _check_vector_store():
    return vector_store.ping()
