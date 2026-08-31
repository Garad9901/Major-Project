# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Environment variables where BLANK and UNSET mean the same thing.

THE DEFECT THIS EXISTS TO REMOVE

    os.getenv(name, default)

applies `default` only when `name` is ABSENT from the environment. A variable
that is PRESENT but empty returns `""`. Docker Compose sets a variable to empty
rather than omitting it for the extremely common shape

    RAG_AGENT_RO_HOST: ${RAG_AGENT_RO_HOST:-}

so an operator who blanks a value out — which is exactly what someone does when
they decide they do not need a separate one — gets an empty string where the
code's own comment promises a fallback. Verified:

    VERIFICATION_MODEL=  ->  ''   (documented as: use LLM_MODEL)

That one was fixed for model names in ae9cb62 (`ollama.model_from_env`). The
same shape appeared in nine database settings and one allowlist path, all
written as a nested chain:

    os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres"))

Blank RAG_AGENT_RO_HOST there produces an empty HOSTNAME, and the nested inner
getenv is never even consulted.

WHY THIS IS THE MODULE AND ollama.model_from_env IS THE ALIAS
There is one implementation, here. `model_from_env` remains as the name the
agent modules use, because "which model" reads better at those call sites than
"which environment variable", but it delegates.

A NOTE ON sync_worker
sync_worker is a separate service whose Docker build context is ./sync_worker,
so it cannot import this module. It carries a four-line copy, marked as such,
pointing here. That duplication is a deliberate consequence of the service
boundary rather than an oversight — see sync_worker/config.py.
"""

import os


def env_or(name, fallback):
    """Return the environment value for `name`, or `fallback` if blank/unset.

    Whitespace-only counts as blank: a value that survives a copy-paste as
    " " is not a hostname, and treating it as one produces a connection error
    far from the cause.
    """
    value = os.getenv(name, "")
    if not isinstance(value, str):
        return value or fallback
    return value.strip() or fallback


def env_chain(*names, default=None):
    """First non-blank value among `names`, else `default`.

    For the RAG_AGENT_RO_* / POSTGRES_* pattern, where the second name is the
    documented fallback for the first. Written as a chain rather than nested
    env_or calls so the call site reads as the precedence order it is.
    """
    for name in names:
        value = env_or(name, None)
        if value is not None:
            return value
    return default
