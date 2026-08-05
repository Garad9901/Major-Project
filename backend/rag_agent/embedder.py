# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

# Same model/config sync_worker embeds rows with — a query embedded with a
# different model would land in a different vector space and every
# similarity score would be meaningless.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def embed_text(text):
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    embedding = ollama.embeddings(EMBEDDING_MODEL, text)
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"expected a {EMBEDDING_DIM}-dim embedding from {EMBEDDING_MODEL}, got {len(embedding)}"
        )
    return embedding
