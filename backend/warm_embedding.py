# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Load the embedding model into memory at startup. Best-effort, never fatal.

WHY THIS IS NOT IN ollama-pull WITH THE OTHER MODELS
It cannot be. ollama-pull warms the chat models with `ollama run`, but there is
no `ollama embed` subcommand, and that image ships neither wget nor curl — so
there is no way to issue an embedding request from inside it. The backend has
Python and an HTTP client, so the warm-up happens here instead.

WHY IT MATTERS AT ALL, GIVEN THE MODEL IS SMALL
nomic-embed-text is ~376 MB and loads in about a second, so this is not the
15-minute cold start that motivated the warm-up work. It matters because
/api/health/ now reports "warming" and returns 503 until every configured model
is resident. Without this, a fresh deployment would sit at 503 indefinitely,
waiting for a model that nothing had yet asked for — a worse failure than the
one the readiness gate was added to fix.

FAILURE IS NOT FATAL. If Ollama is slow or down, the backend must still start:
the health endpoint will keep reporting "warming", which is the truth, and the
model will load on first use.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import ollama  # noqa: E402


def main():
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    try:
        ollama.embeddings(model, "warm")
    except Exception as exc:  # noqa: BLE001 - any failure is non-fatal here
        print(f"[warm] could not warm {model}: {type(exc).__name__}")
        print("[warm] health will report 'warming' until it loads on first use")
        return 0
    print(f"[warm] {model} is resident")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
