# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Inline answer verification, behind a feature flag.

WHAT CHANGED
verify_and_correct() existed but was only ever called from the experimental
evaluation harness (experiments/runner.py). Nothing on the live request path
invoked it, so answers users actually received were never fact-checked. This
module puts it on the live path.

THE MEASURED COST — read this before leaving it on
Verification is not free: it is one further LLM call to extract and check the
claims, plus a second call to rewrite the answer when something is flagged.

It also does the MOST work of any step: it re-reads the question, the complete
answer AND all the evidence, and — unlike synthesis — cannot stream, so the
whole verdict must be generated before anything returns.

Measured on this hardware with VERIFICATION_MODEL=qwen2.5:3b, timing the
verification call in isolation:

    question shape      answer     verification     total     overhead
    ----------------------------------------------------------------
    SQL (a count)         ~30 s          19.9 s     ~50 s        +66%
    RAG (5 passages,     ~140 s         120.9 s    ~260 s        +86%
         7,014 chars)

Because local inference serialises (see orchestrator/concurrency.py), that
overhead comes straight off throughput.

    An earlier version of this note recorded 9.7 s + 9.5 s = 19.1 s (+98%).
    Those numbers are obsolete: they were taken before the faculty-development
    dataset existed, when the schema prompt was small and retrieved passages
    were short course descriptions. The percentage is not far off; the absolute
    seconds are five to thirteen times larger. Re-measure after any change to
    the corpus or the model rather than trusting a recorded figure.

KNOWN FAILURE ON THE LONGEST ANSWERS
With the 7b model, RAG verification exceeded even a 240 s read timeout and every
descriptive question came back unverified. Switching VERIFICATION_MODEL to
qwen2.5:3b brought it inside the timeout — but at ~121 s it is still the single
slowest step, and the longest answers can still time out. When that happens the
user keeps their answer and it is simply marked unverified (verify() never
raises), which is the intended degradation, not a fault.

WHY IT IS STILL ON BY DEFAULT
The system answers questions about fees, prerequisites and timetables using a
7B model that demonstrably gets things wrong: during Phase 4 testing the SQL
agent generated `WHERE code = 'DBS'` for a course whose code is CS310 and
confidently reported that no record existed. An assistant that is wrong quickly
is worse for a student than one that is right slowly. Turn it off only after
deciding that speed matters more than accuracy for your users.

    ENABLE_VERIFICATION=false   disables it entirely

HOW IT WORKS ON THE STREAMING PATH
The answer is streamed to the user as it is generated, exactly as before —
verification cannot begin until a complete answer exists, so buffering the whole
answer to verify it first would destroy the streaming experience AND add the
verification delay before the user sees a single word.

Instead the answer streams normally, verification runs afterwards, and a
correction notice is appended if anything was flagged. The user sees an answer
promptly and sees the correction a few seconds later. The alternative — silently
showing an unverified answer — is what this replaces.
"""

import logging
import os

logger = logging.getLogger("orchestrator")


def is_enabled():
    """Read at call time, not import time, so tests and the shell can toggle it."""
    return os.getenv("ENABLE_VERIFICATION", "true").strip().lower() in (
        "true", "1", "yes", "on",
    )


# Prefix for the appended notice. Deliberately plain: a student reading it
# should understand the assistant corrected itself, without jargon.
CORRECTION_HEADER = "\n\n---\n**Correction:** "

UNVERIFIABLE_NOTE = (
    "\n\n---\n*Note: part of this answer could not be confirmed against the "
    "college records. Please check with the office before relying on it.*"
)

# Shown when the checker did not RUN to completion at all — as opposed to
# running and flagging something, which is UNVERIFIABLE_NOTE above.
#
# WHY THIS EXISTS
# verify() deliberately never raises: losing an answer the user already read
# because the fact-checker broke would be worse than showing it. But the
# original code returned an empty trailing string on that path, so an answer
# whose verification TIMED OUT rendered identically to one that had been checked
# and passed. Nothing in the SPA reads the `verification` field in the `done`
# event, so the user had no signal of any kind.
#
# That inverted the whole point of the feature. Verification times out on the
# LONGEST answers (see the note above: ~121 s for a retrieval answer, against a
# 240 s read timeout) — which are the multi-part, many-claim answers most likely
# to contain a mistake. The failure was therefore concentrated exactly where the
# check mattered most, and it was invisible.
UNVERIFIED_NOTE = (
    "\n\n---\n*Note: this answer could not be fact-checked — the checker did not "
    "finish in time. Please confirm anything important with the college office.*"
)


def verify(question, route, answer, sql_result=None, rag_chunks=None, web_pages=None):
    """Run verification over a completed answer.

    Returns (final_answer, trailing_text, meta). `trailing_text` is what should
    be appended to a stream that has already emitted `answer`; it is empty when
    nothing needed saying.

    NEVER raises. A verification failure must not cost the user an answer that
    was already produced successfully — if the checker itself breaks, the
    unverified answer is still better than an error page.
    """
    if not is_enabled():
        return answer, "", {"verification": "disabled"}

    try:
        # Imported lazily: verification_agent pulls in Django models, and this
        # module is imported by orchestrator.service at load time.
        from verification_agent.service import verify_and_correct

        result = verify_and_correct(
            question, route, answer, sql_result=sql_result, rag_chunks=rag_chunks,
            web_pages=web_pages,
        )
    except Exception:
        logger.exception("verification failed for question=%r — returning unverified answer", question)
        # The answer is kept, but it is LABELLED. See UNVERIFIED_NOTE.
        return answer, UNVERIFIED_NOTE, {"verification": "error"}

    flagged = [c for c in result.claims if not c["supported"]]
    meta = {
        "verification": "ran",
        # How many claims were EXAMINED, which since the switch to a
        # problems-only verdict is no longer the same as len(result.claims) —
        # that now counts flagged claims on the LLM tier.
        "claims_checked": getattr(result, "checked_count", None) or len(result.claims),
        "claims_flagged": len(flagged),
        "corrected": result.was_corrected,
        # Which tier settled it: direct matching (no LLM) or the model.
        "tier": "fast" if getattr(result, "fast_path", False) else "llm",
        "run_id": str(result.run_id) if result.run_id else None,
    }

    if not flagged:
        return result.final_answer, "", meta

    if result.was_corrected and result.final_answer != answer:
        # Something was wrong AND the checker produced a better answer. Show it.
        trailing = CORRECTION_HEADER + result.final_answer.strip()
    else:
        # Something was flagged but could not be corrected from the source data.
        # Say so rather than leaving an unmarked claim standing.
        trailing = UNVERIFIABLE_NOTE

    logger.info(
        "verification flagged %d/%d claim(s) for question=%r corrected=%s",
        len(flagged), len(result.claims), question, result.was_corrected,
    )
    return result.final_answer, trailing, meta
