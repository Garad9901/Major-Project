# Copyright (c) 2026 Yash Garad. All rights reserved.

import math
import re
from difflib import SequenceMatcher

from rag_agent.embedder import embed_text

DEFAULT_THRESHOLD = 0.75


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def string_similarity(a, b):
    """Cheap lexical overlap via difflib — a secondary signal alongside the
    semantic score, useful for spotting cases where the wording matches
    closely vs cases where only the meaning does."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def semantic_similarity(a, b):
    """Cosine similarity of the two answers' embeddings (nomic-embed-text).
    Returns None if embedding fails so the caller can fall back to the
    string score rather than silently scoring 0."""
    try:
        va = embed_text(a or "")
        vb = embed_text(b or "")
    except Exception:
        return None
    return _cosine(va, vb)


def score_answer(final_answer, ground_truth, threshold=DEFAULT_THRESHOLD):
    """Returns a dict with both similarity scores and a correct/incorrect
    verdict. Correctness is decided on the semantic score when available
    (meaning matters more than exact wording for QA), falling back to the
    string score if embeddings are unavailable."""
    sem = semantic_similarity(final_answer, ground_truth)
    stri = string_similarity(final_answer, ground_truth)

    basis = sem if sem is not None else stri
    correct = basis >= threshold

    return {
        "semantic_similarity": round(sem, 4) if sem is not None else None,
        "string_similarity": round(stri, 4),
        "threshold": threshold,
        "correct": correct,
        "correctness_basis": "semantic" if sem is not None else "string",
    }
