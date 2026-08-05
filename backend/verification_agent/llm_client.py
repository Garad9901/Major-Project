# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# Honour the same OLLAMA_READ_TIMEOUT as common/ollama.py.
#
# This module talks to Ollama directly rather than through common.ollama, and
# used to hardcode timeout=120 in both calls below — so raising
# OLLAMA_READ_TIMEOUT fixed the synthesis step and silently left verification
# still failing at 120s. On a CPU-only machine, a retrieval-heavy answer made
# every RAG question log "verification failed ... returning unverified answer".
#
# Verification needs AT LEAST as long as synthesis, not less: these calls use
# "stream": False, so this timeout must cover generating the WHOLE response,
# whereas the streaming synthesis call only has to reach its first token.
_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "5"))
_READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "120"))
_TIMEOUT = (_CONNECT_TIMEOUT, _READ_TIMEOUT)
# LLM_MODEL is the single knob for the model all agents use; VERIFICATION_MODEL
# is an optional per-agent override that defaults to it.
VERIFICATION_MODEL = os.getenv("VERIFICATION_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))

VERIFY_SYSTEM_PROMPT = """You are a fact-checking verifier for a college information assistant. You are given a final answer that was generated for a user's question, plus the raw source data (SQL query results and/or RAG passages) that answer was supposed to be based on.

Your job: break the answer down into its individual factual claims — specific facts, numbers, names, dates. Skip filler phrases and general statements that don't assert a checkable fact. For EACH claim, check whether it is directly supported by the raw source data provided.

For each claim, output:
- "text": the claim, quoted or closely paraphrased from the answer
- "supported": true if the raw source data directly confirms this claim, false if the source data contradicts it or contains no information about it at all
- "confidence": a number from 0.0 to 1.0 — how confident you are in this supported/not-supported judgment
- "evidence": a short quote or reference to the specific source data that supports or contradicts the claim, or the literal string "no relevant source data found" if there is nothing relevant
- "correct_value": ONLY set this if supported is false AND the source data actually contains the correct fact (i.e. the answer got a real, checkable fact wrong). If supported is false because the claim was invented from nothing the source data ever mentioned, set this to null.

Be strict. The source data is the only ground truth — if a claim isn't in it, it isn't supported, no matter how plausible the claim sounds.

Respond with ONLY a JSON object of the form: {"claims": [...]}
"""

CORRECT_SYSTEM_PROMPT = """You are correcting a previously generated answer for a college information assistant, based on a fact-check that just ran against it.

You will be given the original answer and a list of flagged claims. For each flagged claim:
- If a "correct_value" is given, replace that specific incorrect claim with the correct information, keeping the rest of the answer's wording and flow intact.
- If no correct_value is given (the claim could not be verified against the database at all — it was invented), rewrite that specific part to clearly state it could not be verified against the database. Do not silently delete it without any indication, and do not leave the unverified claim stated as if it were fact.

Leave every part of the answer that was NOT flagged exactly as it was — only touch the flagged parts. Return ONLY the corrected answer text. No explanation, no meta-commentary about the correction process, no mention of "flagged claims" or "verification".
"""


def verify_claims(question, answer, sql_section, rag_section):
    user_prompt = f"""Question: {question}

Raw SQL data:
{sql_section}

Raw RAG passages:
{rag_section}

Answer to verify:
{answer}"""

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": VERIFICATION_MODEL,
            "messages": [
                {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def correct_answer(question, original_answer, flagged_claims):
    claims_block = "\n".join(
        f"- claim: {c['text']}\n"
        f"  correct_value: {c['correct_value'] if c.get('correct_value') else 'null (unverifiable — not in source data)'}"
        for c in flagged_claims
    )

    user_prompt = f"""Question: {question}

Original answer:
{original_answer}

Flagged claims:
{claims_block}

Write the corrected answer."""

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": VERIFICATION_MODEL,
            "messages": [
                {"role": "system", "content": CORRECT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()
