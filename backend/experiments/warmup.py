# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Warm up the local models before timing, so the first real question isn't
penalised by Ollama loading a multi-GB model into memory (cold start). Timing
that would skew the latency numbers a research paper reports."""

from rag_agent.embedder import embed_text
from router_agent.llm_client import classify_question


def warm_up_models():
    errors = []
    try:
        embed_text("warmup")
    except Exception as exc:
        errors.append(f"embedding warmup failed: {exc}")
    try:
        # Any chat call loads qwen2.5:7b; the router prompt is the cheapest.
        classify_question("warmup")
    except Exception as exc:
        errors.append(f"llm warmup failed: {exc}")
    return errors
