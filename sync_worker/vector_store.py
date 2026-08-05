# Copyright (c) 2026 Yash Garad. All rights reserved.

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=config.QDRANT_URL)
        _ensure_collection(_client)
    return _client


def _ensure_collection(client):
    existing = {c.name for c in client.get_collections().collections}
    if config.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBEDDING_DIM, distance=Distance.COSINE),
        )


def point_id_for(table, pk):
    # Deterministic UUID from (table, pk) so re-embedding the same row on a
    # later sync updates its existing point instead of creating a duplicate.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{table}:{pk}"))


def upsert_point(table, pk, vector, text, last_updated):
    client = get_client()
    client.upsert(
        collection_name=config.QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=point_id_for(table, pk),
                vector=vector,
                payload={
                    "table": table,
                    "row_id": pk,
                    "last_updated": last_updated,
                    "text": text,
                },
            )
        ],
    )


def indexed_row_ids(table):
    """Every row_id currently indexed for `table`, mapped to its point id.

    Used to find points whose source row no longer exists. Pages through the
    collection rather than assuming one request returns everything.
    """
    client = get_client()
    found = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="table", match=MatchValue(value=table))]
            ),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            found[p.payload.get("row_id")] = p.id
        if offset is None:
            break
    return found


def delete_points(point_ids):
    """Remove points by id. No-op on an empty list."""
    point_ids = list(point_ids)
    if not point_ids:
        return 0
    client = get_client()
    client.delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=PointIdsList(points=point_ids),
    )
    return len(point_ids)


def search(query_vector, limit=5, table_filter=None):
    client = get_client()
    query_filter = None
    if table_filter:
        query_filter = Filter(must=[FieldCondition(key="table", match=MatchValue(value=table_filter))])

    response = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
    )
    return response.points
