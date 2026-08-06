# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Routing without a 7B model call.

WHY
Routing is a four-way choice between SQL, RAG, BOTH and WEB. It was being made
by qwen2.5:7b reading a ~1,200-token few-shot prompt. On CPU that prompt read
alone costs tens of seconds before a single output token — to produce about
twenty tokens of JSON. It is the most expensive decision in the pipeline
measured against how little information it carries.

THREE TIERS, CHEAPEST FIRST

  1. RULES        microseconds. Deterministic keyword and shape matching.
                  Handles the overwhelming majority of real questions, because
                  real questions announce their type: "how many" is a count,
                  "describe" is prose, "when does term start" is the calendar.

  2. EMBEDDINGS   ~40ms warm. Cosine similarity against labelled exemplars using
                  nomic-embed-text, which is already loaded for RAG. Used when
                  the rules find nothing or find a tie.

  3. LLM          seconds. The original prompt, but on ROUTER_MODEL (a 3B by
                  default) with a hard output cap. Reached only when tiers 1 and
                  2 are both unconfident.

WHAT THIS IS NOT
It is not a claim that keyword matching understands language. It is a claim that
this specific four-way choice is mostly decidable from surface form, that being
wrong is cheap and recoverable (a misroute yields a worse answer, never an
unsafe one — the SQL guard and the read-only role are unaffected by routing),
and that tier 3 still exists for genuinely ambiguous input.

ACCURACY IS MEASURED, NOT ASSUMED. See router_agent/tests.py for the labelled
set and the accuracy floor the tests enforce.
"""

import logging
import os
import re
import threading

logger = logging.getLogger("router_agent")

# Below this cosine similarity the embedding tier declines to answer and the
# question falls through to the LLM. Chosen from the measured separation on the
# labelled set rather than picked round: see tests.
EMBED_CONFIDENCE = float(os.getenv("ROUTER_EMBED_CONFIDENCE", "0.62"))

# Set false to force every question through the LLM router (useful to A/B the
# accuracy of this module against it on real traffic).
FAST_ROUTER_ENABLED = os.getenv("FAST_ROUTER", "true").strip().lower() in (
    "true", "1", "yes", "on",
)


# --- tier 1: rules -------------------------------------------------------------
#
# Ordered by specificity. WEB is checked first because its vocabulary is the most
# distinctive and the most costly to get wrong: a term-date question answered
# from the database returns nothing useful, because term dates are not in it.

# Published-page vocabulary. These describe things that live on a calendar or a
# notice board, not in a table.
_WEB_PATTERNS = [
    r"\bacademic calendar\b", r"\bterm dates?\b", r"\bsemester (start|begin|end)",
    r"\bwhen does .{0,30}(term|semester|session) ", r"\bholidays?\b", r"\bvacation\b",
    r"\badmission notices?\b", r"\bcirculars?\b", r"\bannouncements?\b",
    r"\bnotice board\b", r"\bapplication deadline\b", r"\bprospectus\b",
    r"\blast date (to|for)\b", r"\bofficial (page|website|notice)\b",
    r"\biana\b", r"\bexample\.(com|org|net)\b", r"\breserved (example )?domains?\b",
]

# Aggregate / lookup vocabulary: something with one well-defined answer.
_SQL_PATTERNS = [
    r"\bhow many\b", r"\bhow much\b", r"\bcount\b", r"\bnumber of\b",
    r"\bwhat is the (average|mean|median|total|sum|maximum|minimum|highest|lowest)\b",
    r"\baverage\b", r"\btotal\b", r"\bsum of\b", r"\bpercentage\b", r"\bproportion\b",
    r"\blist (all|every|the)\b", r"\bshow me (all|every|the list)\b",
    r"\bwhich .{0,40}\b(has|have) the (highest|lowest|most|fewest|largest|smallest)\b",
    r"\brank(ed|ing)? by\b", r"\bsorted by\b", r"\btop \d+\b",
    r"\bwhen is the (exam|class|lecture)\b",
    # One optional adjective before the noun. Without it "what is the TUITION
    # fee" did not match, and the question fell through to the descriptive
    # vocabulary on the word "describe" later in the sentence — routing a
    # fee-plus-description question to RAG alone, so the fee was never looked up.
    r"\bwhat (is|are) the (\w+\s+)?(fee|fees|cost|amount|price|credits?|duration)\b",
    r"\bmore than \d+\b", r"\bfewer than \d+\b", r"\bat least \d+\b",
    r"\bbreakdown by\b", r"\bgrouped by\b", r"\bper (department|rank|semester)\b",
]

# Prose vocabulary: open-ended, no single field to look up.
_RAG_PATTERNS = [
    r"\bdescribe\b", r"\btell me about\b", r"\boverview\b", r"\bsummar(y|ise|ize)\b",
    r"\bcharacteris|characteriz", r"\bwhat does .{0,40}\bcover\b",
    r"\bexplain\b", r"\bwhat is .{0,30}\blike\b", r"\bhow would you\b",
    r"\bin general\b", r"\bstrengths?\b", r"\bweaknesses?\b", r"\bcompare\b",
    r"\bwhy (did|is|are|does)\b", r"\bwhat (are|is) the (main|key) (theme|point|finding)",
    r"\bgive (me )?an? (overview|account|sense)\b", r"\bnarrative\b", r"\bprofile of\b",
]

_WEB_RE = [re.compile(p, re.I) for p in _WEB_PATTERNS]
_SQL_RE = [re.compile(p, re.I) for p in _SQL_PATTERNS]
_RAG_RE = [re.compile(p, re.I) for p in _RAG_PATTERNS]


def _hits(patterns, text):
    return [p.pattern for p in patterns if p.search(text)]


def classify_by_rules(question):
    """Returns (route, reason, confident). `confident` False means fall through."""
    text = " " + question.strip() + " "

    web = _hits(_WEB_RE, text)
    sql = _hits(_SQL_RE, text)
    rag = _hits(_RAG_RE, text)

    # WEB wins outright. Its vocabulary does not overlap the other two in
    # practice, and a calendar question routed to SQL cannot be answered at all.
    if web and not (sql and rag):
        return "WEB", f"published-page vocabulary ({len(web)} match)", True

    # Both kinds of ask in one sentence is exactly what BOTH is for. Requiring a
    # conjunction avoids treating "describe how many..." as two asks — that is
    # one ask, phrased loosely.
    if sql and rag and re.search(r"\b(and|also|plus|as well as)\b|,", text, re.I):
        return "BOTH", f"aggregate ({len(sql)}) and descriptive ({len(rag)}) ask in one question", True

    if sql and not rag:
        return "SQL", f"aggregate/lookup vocabulary ({len(sql)} match)", True
    if rag and not sql:
        return "RAG", f"descriptive vocabulary ({len(rag)} match)", True

    # Tie with no conjunction, or nothing matched at all.
    return None, "no confident rule match", False


# --- tier 2: embeddings --------------------------------------------------------
#
# Exemplars are the router prompt's own worked examples plus the documented
# check questions from RUNBOOK, so this tier agrees with the LLM tier by
# construction on everything the prompt already covered.

_EXEMPLARS = {
    "SQL": [
        "How many faculty members are in the Computer Science department?",
        "List all programs that take longer than 3 years to complete.",
        "When is the exam for course CS310?",
        "What is the average AI tool adoption score for Professors?",
        "How many faculty in Engineering have a competency level of Expert?",
        "What is the tuition fee for the Computer Science program?",
        "Which department has the most faculty?",
        "How many rooms are in the Science building?",
    ],
    "RAG": [
        "What does the Machine Learning Fundamentals course cover?",
        "Tell me about the Mathematics department.",
        "Give me an overview of how Computer Science is doing on faculty development.",
        "Which departments would you characterise as strongest at digital teaching?",
        "Describe the research culture of the Medicine department.",
        "What are the main themes in the faculty development profiles?",
        "Explain what the competency levels mean in practice.",
    ],
    "BOTH": [
        "What is the tuition fee for Computer Science, and can you describe what the program covers?",
        "How many faculty are in Medicine, and how would you describe their development needs?",
        "How many Lecturers are there and what is their digital capability like?",
        "Give the count of Expert faculty and explain what that suggests.",
    ],
    "WEB": [
        "When does the next semester start?",
        "Are there any new admission notices?",
        "What are the term dates for this academic year?",
        "Is there a circular about the exam schedule?",
        "When is the last date to apply?",
    ],
}

_centroids = None
_centroid_lock = threading.Lock()


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _ensure_centroids(embed_fn):
    """Embed the exemplars once per process, on first use.

    Lazy rather than at import: embedding ~24 short strings costs about a second
    warm, and paying that during Django startup would slow every management
    command and every test run that never routes anything.
    """
    global _centroids
    if _centroids is not None:
        return _centroids
    with _centroid_lock:
        if _centroids is not None:
            return _centroids
        built = {}
        for route, examples in _EXEMPLARS.items():
            vectors = []
            for text in examples:
                try:
                    vectors.append(embed_fn(text))
                except Exception:
                    logger.warning("router: could not embed exemplar %r", text[:40])
            if vectors:
                dim = len(vectors[0])
                built[route] = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
        _centroids = built
        logger.info("router: built %d exemplar centroids", len(built))
        return _centroids


def classify_by_embedding(question, embed_fn):
    """Returns (route, reason, confident)."""
    try:
        centroids = _ensure_centroids(embed_fn)
        if not centroids:
            return None, "no centroids", False
        vector = embed_fn(question)
    except Exception as exc:
        logger.warning("router: embedding tier unavailable (%s)", exc)
        return None, "embedding unavailable", False

    scores = sorted(
        ((route, _cosine(vector, centroid)) for route, centroid in centroids.items()),
        key=lambda pair: pair[1], reverse=True,
    )
    best_route, best_score = scores[0]
    runner_score = scores[1][1] if len(scores) > 1 else 0.0

    if best_score < EMBED_CONFIDENCE:
        return None, f"nearest exemplar only {best_score:.2f}", False
    # A near-tie is not a decision. Sending it to the LLM is the honest move.
    if best_score - runner_score < 0.02:
        return None, f"ambiguous ({best_score:.2f} vs {runner_score:.2f})", False
    return best_route, f"nearest exemplar set ({best_score:.2f})", True
