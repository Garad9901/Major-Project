# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

import requests

from common import llm_metrics

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

# Output caps. Both of these bound GENERATION, which is the expensive half at
# ~9 tok/s — they do not bound how much the model reads.
#
# The verdict is now a short JSON object listing only problems (see
# VERIFY_SYSTEM_PROMPT), so 400 tokens is generous: it fits several flagged
# claims with evidence. A correction rewrites an answer, so it needs room for
# one — capped at roughly the synthesis budget rather than tightly.
# Raised from 400 after observing truncation in production logs.
#
# At 400 the model ran out of budget mid-string on retrieval answers — it was
# pasting whole retrieved passages into the "evidence" field, so three flagged
# claims exhausted it. The JSON then failed to parse, and (before the fix in
# service._parse_claims) a failed parse read downstream as "nothing flagged",
# i.e. a clean pass. A truncated safety check that looks like a passing one is
# the worst possible outcome, so this is now generous AND the evidence field is
# explicitly capped in the prompt.
VERIFY_NUM_PREDICT = int(os.getenv("VERIFY_NUM_PREDICT", "900"))
CORRECT_NUM_PREDICT = int(os.getenv("CORRECT_NUM_PREDICT", "600"))

# REPORT ONLY THE PROBLEMS. THIS IS A LATENCY DECISION AS MUCH AS A PROMPT ONE.
#
# This prompt previously asked for one full object per claim — text, supported,
# confidence, evidence, correct_value — for EVERY claim including the ones that
# passed. On a retrieval answer that is thirteen objects of roughly sixty tokens
# each: about 1,500 output tokens, generated at ~9 tok/s on this hardware.
#
# Measured: verification cost 168-170s on RAG answers, MORE than the synthesis
# that produced them, and almost all of it was spent writing out claims that
# were fine. The common case — nothing wrong — was the most expensive thing the
# pipeline did.
#
# Emitting only UNSUPPORTED claims plus a count makes the common case
# {"checked": 13, "unsupported": []} — about a dozen tokens instead of 1,500.
# Nothing needed downstream is lost: the correction step only ever consumed
# flagged claims, and the metric worth keeping (how many claims were examined
# versus how many were flagged) is still recorded.
VERIFY_SYSTEM_PROMPT = """You are a fact-checking verifier for a college information assistant. You are given a final answer that was generated for a user's question, plus the raw source data (SQL query results and/or RAG passages) that answer was supposed to be based on.

Your job: mentally break the answer into its individual factual claims — specific facts, numbers, names, dates. Skip filler phrases and general statements that don't assert a checkable fact. Check each one against the raw source data.

Then report ONLY the claims that are NOT supported. Do not list claims that are fine — they are the normal case and listing them wastes time.

A claim is NOT supported if the source data contradicts it, or if the source data contains no information about it at all.

Output a JSON object with exactly two keys:
- "checked": an integer, how many factual claims you examined in total
- "unsupported": a list — EMPTY if every claim was supported. Each entry has:
    - "text": the unsupported claim, quoted or closely paraphrased from the answer
    - "confidence": 0.0 to 1.0, how sure you are that it is unsupported
    - "evidence": AT MOST 15 WORDS on what the source says instead, or "not in source". Do NOT quote or paste the passage — a long quote here truncates the response and the whole check is lost.
    - "correct_value": the correct fact IF the source data actually contains it; otherwise null

Be strict. The source data is the only ground truth — if a claim isn't in it, it isn't supported, no matter how plausible it sounds.

If everything checks out, respond with exactly: {"checked": <n>, "unsupported": []}
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
            "options": {"temperature": 0, "num_predict": VERIFY_NUM_PREDICT},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    # This module posts to Ollama directly rather than via common.ollama, so it
    # has to record its own timings — otherwise the slowest stage in the
    # pipeline would be the one stage missing from the profile.
    llm_metrics.record("verify", VERIFICATION_MODEL, body)
    return body["message"]["content"]


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
            "options": {"temperature": 0, "num_predict": CORRECT_NUM_PREDICT},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    llm_metrics.record("correct", VERIFICATION_MODEL, body)
    return body["message"]["content"].strip()
