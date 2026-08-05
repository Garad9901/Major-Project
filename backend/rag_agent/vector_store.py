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


def newest_indexed_updated_at(table, timeout=3):
    """The latest source `updated_at` present in the index for one table.

    Returns a datetime, or None if the table has no points (or Qdrant is
    unreachable — the caller is a health check and treats both the same way).

    Used by the status page to answer a question that no liveness probe can:
    not "is Qdrant up" but "is what Qdrant holds still current". Those come
    apart exactly when it matters — a sync worker that has crashed, or is
    running but wedged, leaves every component pingable and the index frozen.

    Scrolls with a payload-only, vector-less request ordered by the indexed
    timestamp. Qdrant cannot sort by an unindexed payload field, so this pages
    through instead; the collection is small (tens to low hundreds of points)
    and this runs on a 15-second status refresh, not per request.
    """
    from datetime import datetime

    try:
        client = QdrantClient(url=QDRANT_URL, timeout=timeout)
        newest = None
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter={"must": [{"key": "table", "match": {"value": table}}]},
                limit=256,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for point in points:
                # "last_updated" is the key sync_worker writes (see
                # sync_worker/vector_store.upsert_point) — NOT "updated_at",
                # which is what the source column is called. Reading the wrong
                # one returns None for every point, which this function cannot
                # distinguish from "Qdrant is unreachable", so the freshness
                # check would report a permanent false alarm.
                raw = (point.payload or {}).get("last_updated")
                if not raw:
                    continue
                try:
                    seen = datetime.fromisoformat(str(raw))
                except ValueError:
                    continue
                if newest is None or seen > newest:
                    newest = seen
            if offset is None:
                break
        return newest
    except Exception:
        return None
