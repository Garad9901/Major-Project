# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from qdrant_client import QdrantClient

from common.exceptions import VectorStoreUnavailable

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "college_docs")
# Bound how long we wait on Qdrant so an unreachable vector store fails fast.
QDRANT_TIMEOUT_S = float(os.getenv("QDRANT_TIMEOUT", "5"))

_client = None


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=QDRANT_TIMEOUT_S)
    return _client


def search(query_vector, limit=5):
    # No table filter needed: college_docs only ever contains points from
    # the descriptive tables (departments/faculty/programs/courses) — that's
    # enforced upstream by sync_worker only embedding those (see
    # sync_worker/config.py DESCRIPTIVE_TABLES), not by anything here.
    #
    # Raises VectorStoreUnavailable if Qdrant is unreachable, so callers can
    # fall back to SQL-only or tell the user descriptive search is down.
    try:
        response = get_client().query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
        )
    except Exception as exc:
        raise VectorStoreUnavailable(f"Qdrant search failed: {exc}") from exc
    return response.points


def ping(timeout=3):
    """Lightweight liveness probe for the health endpoint. Returns True if
    Qdrant responds, False otherwise (never raises). Uses a short-lived client
    with its own timeout so a hung Qdrant doesn't stall the health check."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=timeout)
        client.get_collections()
        return True
    except Exception:
        return False
