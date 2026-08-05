# Copyright (c) 2026 Yash Garad. All rights reserved.

import requests

import config


def embed_text(text):
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": config.EMBEDDING_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    embedding = resp.json()["embedding"]
    if len(embedding) != config.EMBEDDING_DIM:
        raise ValueError(
            f"expected a {config.EMBEDDING_DIM}-dim embedding from {config.EMBEDDING_MODEL}, "
            f"got {len(embedding)} — did the model change?"
        )
    return embedding
