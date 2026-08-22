# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import requests

from common import llm_metrics
from common.exceptions import LLMUnavailable

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# (connect, read) timeouts. A short CONNECT timeout means a DOWN Ollama fails
# fast (~5s) instead of hanging. The READ timeout bounds a SLOW Ollama: even if
# it accepts the connection but stalls, the request gives up rather than
# hanging forever. Both are env-tunable.
CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "120"))
_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)

# THE CONTEXT WINDOW IS A SECURITY CONTROL, NOT A TUNING KNOB.
#
# No agent ever set num_ctx, so Ollama applied its own default. With no GPU
# that default is 4096:
#
#     msg="vram-based default context" total_vram="0 B" default_num_ctx=4096
#
# When a prompt exceeds it, Ollama does not error — it silently DISCARDS THE
# FRONT of the prompt. Measured directly (see docs/LATENCY.md, 18 Aug 2026):
# an ~11,000-token system prompt beginning with a canary string was sent with
# num_ctx=4096; prompt_eval_count came back as 2050 and the model had no idea
# the canary existed.
#
# The front of every synthesis prompt is the system prompt, and that is where
# the "# UNTRUSTED CONTENT" rules live — the ones added because a seeded course
# description containing "IGNORE ALL PREVIOUS INSTRUCTIONS" was obeyed verbatim
# (see synthesis_agent/llm_client.py). So a long enough set of retrieved
# passages would have disarmed the injection defences with no error, no log
# line, and no visible change to the answer.
#
# Measured largest real prompt over 300 recorded questions: 3,365 tokens, on
# synthesis — 82% of the way to the old ceiling, and it grows with the number
# of retrieved chunks.
#
# 8192 doubles the headroom. Measured cost of doing so: none. Prefill 29.6 ->
# 29.0 tok/s, generation 7.85 -> 8.10 tok/s, both inside run-to-run noise.
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

# Thread count: DEFAULTS TO AUTO ON PURPOSE.
#
# Ollama sizes its pool from the visible CPU count (22 here — a Core Ultra 9
# 185H is 6 P-cores/12 threads + 8 E-cores + 2 low-power E-cores). A first
# sweep suggested num_thread=14 was 1.47x faster at prefill. Re-measured with
# the configurations ALTERNATING rather than run in sequence, the real effect
# is 1.12x on prefill (29.3 -> 32.8 tok/s, n=3) and -4% on generation, which is
# inside the noise. The first sweep had been measuring machine drift: the same
# default config read 18.6 tok/s in one run and 29.3 tok/s in the next.
#
# 1.12x on prefill is worth ~1.5s of a 28s request. That is not enough to
# justify hardcoding a core count that is correct for exactly one machine and
# wrong for any other, so the default hands the choice back to Ollama. Set
# OLLAMA_NUM_THREAD=14 to take the 1.12x on this specific hardware.
NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", "0"))


def _options(options):
    """Merge the deployment-wide defaults into a caller's options.

    `setdefault`, so an agent that has a reason to override one still can. Both
    values are applied to every model alike: giving two agents different
    num_ctx values for the SAME model would make Ollama reload it on each
    switch, which costs 16s and throws away the prefix cache.
    """
    merged = dict(options or {})
    if NUM_CTX > 0:
        merged.setdefault("num_ctx", NUM_CTX)
    if NUM_THREAD > 0:
        merged.setdefault("num_thread", NUM_THREAD)
    return merged


def chat(model, messages, options=None, response_format=None, label="chat"):
    """Non-streaming chat. Returns the assistant message content string.
    Raises LLMUnavailable if Ollama is unreachable, times out, or errors.

    `label` names this call in the latency profile (see common/llm_metrics.py);
    it has no effect on the request itself.
    """
    payload = {"model": model, "messages": messages, "stream": False, "options": _options(options)}
    if response_format is not None:
        payload["format"] = response_format
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        # Ollama returns its own prompt-read / generation split alongside the
        # content. Recording it here means every agent gets profiled without
        # any agent having to know the profiler exists.
        llm_metrics.record(label, model, body)
        return body["message"]["content"]
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama chat request failed: {exc}") from exc


def chat_stream(model, messages, options=None, label="chat_stream"):
    """Streaming chat. Yields content pieces as they arrive. Raises
    LLMUnavailable on any failure, including the stream dropping mid-answer.

    CLOSING THE RESPONSE IS WHAT MAKES "STOP GENERATING" REAL.
    When the user stops an answer, Django closes this generator, which raises
    GeneratorExit at the `yield` below. Without the `finally`, the underlying
    HTTP connection to Ollama was left for the garbage collector to reclaim
    whenever it got round to it — and until it did, Ollama carried on generating
    the whole answer, holding the only inference slot on a machine that can run
    exactly one at a time. Stopping would have freed the screen and nothing else.

    resp.close() drops the socket, Ollama sees the client disappear and abandons
    the generation. That is the difference between a Stop button and a Hide
    button.
    """
    payload = {"model": model, "messages": messages, "stream": True, "options": _options(options)}
    resp = None
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
                # The final chunk carries the timings for the whole stream.
                # Recorded before the break so a stream the caller abandons
                # (Stop generating) records nothing rather than a partial split
                # that would look like a fast call.
                llm_metrics.record(label, model, chunk)
                break
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama streaming chat failed: {exc}") from exc
    finally:
        # Runs on normal completion, on error, AND on GeneratorExit when the
        # caller closes us because the browser went away.
        if resp is not None:
            resp.close()


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
    """Is the Ollama SERVER reachable? Liveness only.

    NOT A READINESS CHECK, AND THE DIFFERENCE MATTERS. /api/tags lists the
    models on DISK and returns 200 the moment the server is listening —
    regardless of whether any model is loaded into memory. Health used to call
    this and report "llm: up", which is how a fresh deployment reported itself
    healthy for the ~15 minutes it takes to load the models while every question
    timed out. Demonstrated: with all three models explicitly unloaded,
    /api/health/ still returned {"status":"ok","llm":"up"} with HTTP 200.

    Use loaded_models()/is_ready() for readiness.
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def loaded_models(timeout=3):
    """Model names currently RESIDENT in memory, from /api/ps.

    Returns None when Ollama itself cannot be reached, which is a different
    state from "reachable but nothing loaded" and the caller needs to tell them
    apart. An empty list means the server is up and warming.

    WHY RESIDENCY RATHER THAN A TEST GENERATION. Health is polled every 15s by
    the container healthcheck and again by any uptime monitor. A real generation
    per poll would occupy the single inference slot more or less permanently on
    a CPU-only box — the check would become the outage. /api/ps is a cheap read
    of the scheduler's own state and answers the question that actually matters:
    is the model in memory, or will the next question pay a cold load?
    """
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=timeout)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return None


def _same_model(a, b):
    """Compare model names, tolerating an implicit :latest on either side.

    THE TAG IS PART OF THE IDENTITY. A first version compared only the part
    before the colon, which made `qwen2.5:3b` and `qwen2.5:7b` the same model —
    so a deployment with only the 3B resident reported itself ready to serve 7B
    questions, reintroducing the exact bug this function exists to catch. Caught
    by test_partial_residency_is_still_warming.

    An ABSENT tag means "latest", which is the only equivalence allowed here.
    """
    if a == b:
        return True
    a_name, _, a_tag = a.partition(":")
    b_name, _, b_tag = b.partition(":")
    if a_name != b_name:
        return False
    return (a_tag or "latest") == (b_tag or "latest")


def is_ready(models=None, timeout=3):
    """(ready, detail) — can the next question be answered without a cold load?

    `models` defaults to the models this deployment actually uses. A model that
    is configured but not resident means WARMING, not ready: the first question
    to need it pays a load measured in minutes on this hardware, and
    OLLAMA_READ_TIMEOUT will usually fire first.
    """
    # Deduplicated, order preserved. VERIFICATION_MODEL and ROUTER_MODEL are
    # both commonly qwen2.5:3b, and listing it twice in an operator-facing
    # message reads like two separate things are missing.
    seen, wanted = set(), []
    for m in (models if models is not None else _configured_models()):
        if m and m not in seen:
            seen.add(m)
            wanted.append(m)
    resident = loaded_models(timeout=timeout)
    if resident is None:
        return False, "Ollama is not reachable"
    missing = [m for m in wanted if not any(_same_model(m, r) for r in resident)]
    if missing:
        return False, "loading " + ", ".join(missing)
    return True, "loaded: " + ", ".join(resident)


def _configured_models():
    """The models a question can actually reach, from the environment.

    Read at call time rather than import time so a health check reflects the
    running configuration even if it was changed under a restart.
    """
    llm = os.getenv("LLM_MODEL", "qwen2.5:7b")
    return [
        os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        llm,
        # Optional per-agent overrides. Only counted when set to something
        # different, so a deployment that does not use them is not reported as
        # perpetually warming for a model it never loads.
        os.getenv("VERIFICATION_MODEL", "") or "",
        os.getenv("SYNTHESIS_MODEL", "") or "",
        os.getenv("ROUTER_MODEL", "qwen2.5:3b"),
    ]
