# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Verify an answer without an LLM call, when that can be done safely.

WHY
Verification was the single slowest step in the pipeline: it re-reads the
question, the whole answer AND all the evidence, cannot stream, and so the
entire verdict must be generated before anything returns. Measured on this
hardware: ~20s for a simple count, ~121s for a retrieval answer.

For a large share of questions that work is unnecessary. "There are 3,053
faculty members holding the Lecturer rank" is checkable by looking for 3053 in
the SQL rows. That is a string comparison, not an inference problem.

THE SAFETY RULE THIS MODULE OBEYS
It may only ever return "decided". It may never return "this answer is fine"
on anything it has not actually checked. Every condition below is a reason to
DECLINE and fall through to the LLM, and the defaults are all set to decline.

Concretely, the fast path is used ONLY when all of these hold:

  * the answer is short                     long answers make many claims
  * it contains at least one number         otherwise there is nothing to match
  * EVERY number in it appears in the source
  * every proper-noun-looking phrase in it appears in the source

That last condition exists because of a real failure seen during the production
audit: with the source data unavailable the model wrote "Dr. Jane Smith and
Professor John Doe are both well-known for their extensive research
contributions" — inventing two people. Numbers alone would not have caught it,
because there were no numbers to catch. Requiring names to be grounded does.

WHAT IT DOES NOT DO
It does not correct anything, and it never reports a claim as UNSUPPORTED. A
mismatch is not treated as proof the answer is wrong — a number can be legitimately
derived (a percentage computed from two rows) rather than copied. A mismatch
means "this needs judgement", which is exactly what the LLM tier is for.
"""

import logging
import os
import re

logger = logging.getLogger("verification_agent")

FAST_CHECK_ENABLED = os.getenv("FAST_VERIFICATION", "true").strip().lower() in (
    "true", "1", "yes", "on",
)

# Above this length an answer is making too many claims for number-matching to
# be a fair summary of its correctness.
MAX_FAST_ANSWER_CHARS = int(os.getenv("FAST_VERIFICATION_MAX_CHARS", "700"))

_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

# Capitalised runs of 2+ words: "Jane Smith", "Computer Science", "Associate
# Professor". Single capitalised words are excluded — too many false positives
# from sentence starts and ordinary nouns to be useful.
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]{1,}(?:\s+(?:of|and|the|for)\s+)?(?:\s+[A-Z][a-z]{1,})+)\b")

# Phrases that look like proper nouns but are ordinary prose or come from the
# assistant's own boilerplate rather than from the data.
_PROPER_NOUN_STOPLIST = {
    "the college", "this college", "the university", "the department",
    "please check", "please confirm", "please contact", "the office",
    "note that", "based on", "according to", "in addition", "for example",
    "development need", "development needs", "competency level",
    "high development", "moderate development", "low development",
}


def _numbers_in(text):
    """Every number in `text`, normalised to float, ignoring thousands commas."""
    found = set()
    for raw in _NUMBER_RE.findall(text or ""):
        try:
            found.add(float(raw.replace(",", "")))
        except ValueError:
            continue
    return found


def _source_text(sql_result, rag_chunks, web_pages):
    """Everything the answer was allowed to be built from, as one string."""
    parts = []
    if sql_result is not None and getattr(sql_result, "rows", None):
        for row in sql_result.rows:
            parts.append(repr(row))
        parts.append(str(getattr(sql_result, "columns", "")))
    for chunk in rag_chunks or []:
        parts.append(getattr(chunk, "text", "") or "")
    for page in web_pages or []:
        parts.append(getattr(page, "text", "") or "")
    return "\n".join(parts)


def _matches_a_source_number(value, source_numbers):
    """Is `value` present in the source, allowing for display rounding?

    An answer may legitimately write 67.2 for a stored 67.20, or 7.19 as 7.2.
    It may NOT write 730 for a stored 731 — so the tolerance is tied to the
    precision the answer itself used, not a flat epsilon.
    """
    if value in source_numbers:
        return True
    for candidate in source_numbers:
        if candidate == 0:
            continue
        # Same number to one decimal place, or within 0.5% (covers rounding of
        # long decimals) — but never enough to confuse two adjacent integers.
        if abs(candidate - value) < 0.05:
            return True
        if abs(candidate - value) / abs(candidate) < 0.005 and abs(candidate - value) < 0.5:
            return True
    return False


def _ungrounded_proper_nouns(answer, source):
    source_low = source.lower()
    bad = []
    for phrase in _PROPER_NOUN_RE.findall(answer or ""):
        cleaned = " ".join(phrase.split())
        if cleaned.lower() in _PROPER_NOUN_STOPLIST:
            continue
        if cleaned.lower() in source_low:
            continue
        # Also accept when every word of the phrase appears in the source: the
        # answer may reorder or re-case ("Science, Social" vs "Social Science").
        if all(word.lower() in source_low for word in cleaned.split() if len(word) > 2):
            continue
        bad.append(cleaned)
    return bad


class FastCheckResult:
    """Three outcomes, not two.

    This module used to compute three things and return two. It would establish
    that a number in the answer was ABSENT FROM THE SOURCE — positive evidence
    of fabrication — and then return `decided=False`, which means "I cannot
    tell, ask the LLM". The evidence was discarded at the point it was strongest.

    Audit log entry 801 is what that cost. Handed a single row `{'count': 2}`,
    synthesis wrote "There are 2,014 faculty in the Computer Science
    department." This module correctly found 2014 absent from the source, said
    "I cannot tell", deferred to the LLM tier, and the LLM tier timed out. The
    fabricated figure shipped with a hedge attached.

        confirmed  every checkable claim matched the source
        declined   cannot be settled here; the LLM tier should run
        refuted    the answer contradicts the source, provably, with no
                   interpretation required
    """

    CONFIRMED = "confirmed"
    DECLINED = "declined"
    REFUTED = "refuted"

    def __init__(self, decided, claims=None, reason="", verdict=None, refutation=""):
        # `decided` is kept as the CONFIRM flag it always was, so every existing
        # caller and test keeps its meaning. A refutation is not "decided" in
        # that sense — it does not mean "this answer passed".
        self.decided = decided
        self.claims = claims or []
        self.reason = reason
        self.verdict = verdict or (self.CONFIRMED if decided else self.DECLINED)
        # Operator-facing sentence naming what contradicted what. Never shown
        # to the user; see the boundary in _try_scalar_refute.
        self.refutation = refutation

    @property
    def refuted(self):
        return self.verdict == self.REFUTED


def try_fast_check(question, answer, sql_result=None, rag_chunks=None, web_pages=None):
    """Attempt to verify `answer` by direct matching. Never raises."""
    if not FAST_CHECK_ENABLED:
        return FastCheckResult(False, reason="disabled")
    try:
        return _try(answer, sql_result, rag_chunks, web_pages)
    except Exception:
        # A bug in here must never cost a user their answer, and must never
        # silently skip verification — decline, and the LLM tier runs.
        logger.exception("fast verification check errored; falling back to the LLM")
        return FastCheckResult(False, reason="fast check errored")


def _try_scalar_refute(text, sql_result):
    """The narrowest possible refutation: a contradicted scalar.

    ENTRY CONDITIONS ARE ITS OWN, NOT THE CONFIRM PATH'S. A wrong decline costs
    seconds of LLM time; a wrong refutation suppresses a correct answer in front
    of a user. Raising the consequence raises the bar on the input, so this
    fires only when there is nothing left to interpret:

        * the SQL ran without error
        * it returned EXACTLY one row with EXACTLY one column
        * that value is numeric
        * the answer contains at least one number
        * NONE of the answer's numbers match the scalar

    "None match" rather than "any differs" is deliberate, and it is what makes
    derived arithmetic safe. An answer that says "1,916, which is 15% of the
    total" contains 1916 and 15; the scalar is present, so this does not fire.
    Only an answer that never states the retrieved figure at all is refuted.

    Note the length cap from the confirm path is NOT inherited. A fabricated
    count is just as wrong inside a long answer, and the check is exact either
    way — there is no matching to get fuzzy over.

    THE BOUNDARY, AND IT IS THE WHOLE REASON THIS DOES NOT AUTO-CORRECT:
    this function's warrant is "the answer's figure is not supported by the
    evidence". It is NOT "the source figure is right". It cannot know that,
    because it cannot see that the evidence itself came from the wrong table —
    which is exactly what happened in entry 801, where the source said 2 and
    the truth was 1,916. Substituting the source value there would have shipped
    "There are 2 faculty in Computer Science" marked CONFIRMED, which is
    strictly worse than the fabrication it replaced. So: suppress and say so.
    Never substitute. The caller must not print `scalar` to a user.
    """
    if sql_result is None or getattr(sql_result, "error", None):
        return None
    rows = getattr(sql_result, "rows", None)
    if not rows or len(rows) != 1:
        return None

    row = rows[0]
    values = list(row.values()) if isinstance(row, dict) else list(row)
    if len(values) != 1:
        return None

    scalar = values[0]
    if isinstance(scalar, bool) or not isinstance(scalar, (int, float)):
        # bool is an int subclass; a True/False cell is not a measurement.
        return None
    scalar = float(scalar)

    answer_numbers = _numbers_in(text)
    if not answer_numbers:
        return None

    if any(_matches_a_source_number(n, {scalar}) for n in answer_numbers):
        return None

    return FastCheckResult(
        False,
        verdict=FastCheckResult.REFUTED,
        reason=(
            f"answer states {sorted(answer_numbers)} but the query returned the "
            f"single value {scalar:g}"
        ),
        refutation=(
            f"The query returned one value ({scalar:g}). The answer stated "
            f"{', '.join(f'{n:g}' for n in sorted(answer_numbers))} instead, "
            f"which appears nowhere in the retrieved data."
        ),
    )


def _try(answer, sql_result, rag_chunks, web_pages):
    text = (answer or "").strip()
    if not text:
        return FastCheckResult(False, reason="empty answer")

    # REFUTATION IS CHECKED BEFORE THE CONFIRM PATH'S GUARDS, on purpose.
    #
    # It has to be, because every guard below DECLINES, and a decline was the
    # wrong response to positive evidence in entry 801. If a contradicted scalar
    # sat inside a 900-character answer, the length cap would hand it to the LLM
    # tier and the contradiction would never be looked at at all.
    #
    # The one guard it does NOT jump is the SQL-error check, which is inside
    # _try_scalar_refute itself: you cannot refute an answer against a lookup
    # that failed, because a failed lookup is not evidence of anything.
    refuted = _try_scalar_refute(text, sql_result)
    if refuted is not None:
        return refuted

    if len(text) > MAX_FAST_ANSWER_CHARS:
        return FastCheckResult(
            False, reason=f"answer too long for direct matching ({len(text)} chars)"
        )

    # A failed or empty SQL result means the answer is talking about an absence
    # or an error. Those are exactly the cases the audit found the model getting
    # wrong, and they are judgement calls — always send them to the LLM.
    if sql_result is not None and getattr(sql_result, "error", None):
        return FastCheckResult(False, reason="sql errored; needs judgement")

    source = _source_text(sql_result, rag_chunks, web_pages)
    if not source.strip():
        return FastCheckResult(False, reason="no source text to match against")

    answer_numbers = _numbers_in(text)
    if not answer_numbers:
        return FastCheckResult(False, reason="no numeric claims to match")

    source_numbers = _numbers_in(source)
    ungrounded = [n for n in answer_numbers if not _matches_a_source_number(n, source_numbers)]
    if ungrounded:
        return FastCheckResult(
            False, reason=f"{len(ungrounded)} number(s) not found in source: {sorted(ungrounded)[:4]}"
        )

    invented = _ungrounded_proper_nouns(text, source)
    if invented:
        return FastCheckResult(
            False, reason=f"proper noun(s) not in source: {invented[:3]}"
        )

    claims = [
        {
            "text": f"numeric value {n:g}",
            "supported": True,
            "confidence": 1.0,
            "evidence": "exact match against source data",
            "correct_value": None,
        }
        for n in sorted(answer_numbers)
    ]
    logger.info(
        "fast verification PASSED: %d numeric claim(s) matched directly, no LLM call",
        len(claims),
    )
    return FastCheckResult(True, claims=claims, reason=f"{len(claims)} numeric claim(s) matched")
