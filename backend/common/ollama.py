# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import requests

from common.exceptions import LLMUnavailable

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# (connect, read) timeouts. A short CONNECT timeout means a DOWN Ollama fails
# fast (~5s) instead of hanging. The READ timeout bounds a SLOW Ollama: even if
# it accepts the connection but stalls, the request gives up rather than
# hanging forever. Both are env-tunable.
CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "120"))
_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


def chat(model, messages, options=None, response_format=None):
    """Non-streaming chat. Returns the assistant message content string.
    Raises LLMUnavailable if Ollama is unreachable, times out, or errors."""
    payload = {"model": model, "messages": messages, "stream": False, "options": options or {}}
    if response_format is not None:
        payload["format"] = response_format
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama chat request failed: {exc}") from exc


def chat_stream(model, messages, options=None):
    """Streaming chat. Yields content pieces as they arrive. Raises
    LLMUnavailable on any failure, including the stream dropping mid-answer."""
    payload = {"model": model, "messages": messages, "stream": True, "options": options or {}}
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=_TIMEOUT, stream=True
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece
            if chunk.get("done"):
                break
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama streaming chat failed: {exc}") from exc


def embeddings(model, prompt):
    """Returns an embedding vector. Raises LLMUnavailable on failure."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": model, "prompt": prompt},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama embeddings request failed: {exc}") from exc


def ping(timeout=3):
    """Lightweight liveness probe for the health endpoint. Returns True if
    Ollama responds, False otherwise (never raises)."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False
