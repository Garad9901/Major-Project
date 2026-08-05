# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from . import embedder, vector_store

logger = logging.getLogger("rag_agent")


class RetrievedChunk:
    def __init__(self, table, row_id, last_updated, text, score):
        self.table = table
        self.row_id = row_id
        self.last_updated = last_updated
        self.text = text
        self.score = score

    def to_dict(self):
        return {
            "table": self.table,
            "row_id": self.row_id,
            "last_updated": self.last_updated,
            "text": self.text,
            "score": self.score,
        }


def retrieve(question, top_k=5):
    vector = embedder.embed_text(question)
    points = vector_store.search(vector, limit=top_k)

    chunks = [
        RetrievedChunk(
            table=p.payload.get("table"),
            row_id=p.payload.get("row_id"),
            last_updated=p.payload.get("last_updated"),
            text=p.payload.get("text"),
            score=p.score,
        )
        for p in points
    ]

    logger.info(
        "question=%r retrieved=%d chunks top_score=%s",
        question, len(chunks), f"{chunks[0].score:.4f}" if chunks else None,
    )
    return chunks
