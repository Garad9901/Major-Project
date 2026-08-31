# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Conversation context: what the user was just talking about.

THE BUG THIS FIXES
Every question was handled in isolation. Ask "how many departments are there?"
and then "name them", and the second question reached the router, the SQL agent
and synthesis as the bare string "name them" — with no idea what "them" was.
The router could not classify it, the SQL agent could not write a query for it,
and the answer was useless.

TWO MECHANISMS, AND THE ORDER MATTERS

  1. RESOLUTION — rewrite the follow-up into a standalone question.
     "name them" -> "Name the departments."
  2. DIGEST — a short transcript of recent turns, passed to the agents as
     context alongside the question.

Resolution is the one that actually carries the fix, and it is not optional:

  * The RAG agent EMBEDS the question. Embedding "name them" produces a vector
    for a meaningless phrase, and no amount of extra prompt context changes
    that — the only fix is to embed different text.
  * The response cache KEYS on the question. Two unrelated conversations both
    ending in "name them" would otherwise collide and serve each other's
    answers. Keying on the resolved form makes the key carry the context.

The digest is what lets each agent see the conversation as well, and covers the
cases resolution gets subtly wrong — the SQL agent can still see that the last
question was about departments even if the rewrite was clumsy.

THE LATENCY BUDGET, WHICH IS WHY THIS IS CONDITIONAL
Prompt reading is 70.9% of this system's wall time and runs at roughly 40
tokens/sec on the uncached tail (docs/LATENCY.md). Three exchanges of history
is about 200-250 tokens, so attaching it to every agent call on every question
would cost 5-6 seconds PER CALL — on a system where a simple question already
takes 20 seconds.

So history is attached ONLY when the question actually looks like a follow-up.
A self-contained question takes exactly the path it took before this change,
with no added tokens and no extra LLM call. That is the whole reason
`looks_like_followup` exists rather than always loading history.
"""

import logging
import os
import re

logger = logging.getLogger("orchestrator")

# How many QUESTION+ANSWER pairs of history to carry.
#
# Three, not the whole conversation, and not five. The reference being resolved
# is almost always to the immediately preceding turn; the second and third are
# there for "and the one before that" cases. Measured cost of the digest at
# this size is ~200-250 tokens, or 5-6s of prompt reading per agent call that
# receives it. Five exchanges roughly doubles that for cases that, in testing,
# never needed it.
#
# Tunable without a code change if real pilot conversations turn out to refer
# further back — see docs/CONVERSATION_CONTEXT.md for how to tell.
HISTORY_EXCHANGES = int(os.getenv("CONVERSATION_HISTORY_EXCHANGES", "3"))

# Assistant answers are truncated in the digest. A full descriptive answer runs
# to 900 characters and would dominate the context window while contributing
# almost nothing: what disambiguates "them" is the SUBJECT of the previous
# turn, which is in the first sentence or two.
ANSWER_CHARS = int(os.getenv("CONVERSATION_HISTORY_ANSWER_CHARS", "220"))

# Everything from here on in a stored answer is machinery, not conversation:
# the verification note, the correction block, the degradation notes. Feeding
# them back in teaches the model to write more of them.
_APPENDIX_RE = re.compile(r"\n\n---\n.*", re.DOTALL)
_TRAILING_NOTE_RE = re.compile(r"\n\nNote: .*", re.DOTALL)


def _clean_answer(text):
    text = _APPENDIX_RE.sub("", text or "")
    text = _TRAILING_NOTE_RE.sub("", text)
    text = " ".join(text.split())
    if len(text) > ANSWER_CHARS:
        text = text[:ANSWER_CHARS].rsplit(" ", 1)[0] + "…"
    return text


# --- is this a follow-up? ---------------------------------------------------
#
# Deterministic and free. Getting this wrong is cheap in both directions:
#
#   false negative -> the question is treated as standalone, i.e. exactly the
#                     behaviour before this change. No regression.
#   false positive -> history is loaded and a resolution call is made for a
#                     question that did not need it. The resolver returns
#                     self-contained questions unchanged, so the cost is
#                     latency on that one question, not a wrong answer.
#
# Biased towards catching follow-ups, because the failure it prevents is
# user-visible and the failure it causes is not.

# STRONG markers: almost always point at a previous turn. "them" and "those"
# have no other common use in a question about a college.
_STRONG_PRONOUNS = r"(them|they|those|these|their|theirs)"

# WEAK markers: frequently RELATIVE pronouns rather than references backwards.
#
#   "How many faculty are in the department THAT has the most publications?"
#
# is self-contained, and treating it as a follow-up would fire a resolution
# call on a large share of ordinary questions. These therefore only count in a
# SHORT question, where there is not enough text for the word to be doing
# grammatical work — "how does that compare to Medicine" is a real follow-up.
_WEAK_PRONOUNS = r"(it|its|that|this|there|he|she|his|her)"

# Below this length a weak marker is taken as referential. Above it, only a
# strong marker or an explicit continuation counts.
_WEAK_MARKER_MAX_CHARS = int(os.getenv("CONVERSATION_WEAK_MARKER_MAX_CHARS", "45"))

_FOLLOWUP_PATTERNS = [
    # A bare pronoun reference: "name them", "list those"
    re.compile(rf"\b{_STRONG_PRONOUNS}\b", re.IGNORECASE),
    # Ellipsis: the verb and object are inherited from the previous turn.
    re.compile(r"^\s*(what|how) about\b", re.IGNORECASE),
    re.compile(r"^\s*(and|but|so|also|plus)\b", re.IGNORECASE),
    re.compile(r"^\s*(same|similarly|likewise)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+about\b", re.IGNORECASE),
    re.compile(r"^\s*(why|why not)\b\s*\??$", re.IGNORECASE),
    # "the first one", "the second", "which ones"
    re.compile(r"\b(the )?(first|second|third|last|next|other) (one|ones)?\b", re.IGNORECASE),
    re.compile(r"\bwhich ones?\b", re.IGNORECASE),
    # A fragment with no verb at all: "just Engineering?", "by department?"
    re.compile(r"^\s*(just|only|by|for|in)\b[^?.]{0,40}\??\s*$", re.IGNORECASE),
]

# Above this length a question almost always carries its own subject, and the
# pronoun that matched is incidental ("How many faculty are in the department
# that has the most publications?" contains "that" and needs no history).
_MAX_FOLLOWUP_CHARS = int(os.getenv("CONVERSATION_FOLLOWUP_MAX_CHARS", "90"))


_WEAK_PRONOUN_RE = re.compile(rf"\b{_WEAK_PRONOUNS}\b", re.IGNORECASE)


def looks_like_followup(question):
    """Cheap test for whether `question` depends on what came before."""
    q = (question or "").strip()
    if not q:
        return False
    if len(q) > _MAX_FOLLOWUP_CHARS:
        return False
    if any(p.search(q) for p in _FOLLOWUP_PATTERNS):
        return True
    # A weak marker only counts in a short question. See _WEAK_PRONOUNS.
    return len(q) <= _WEAK_MARKER_MAX_CHARS and bool(_WEAK_PRONOUN_RE.search(q))


# --- loading and formatting -------------------------------------------------


class Turn:
    __slots__ = ("role", "text")

    def __init__(self, role, text):
        self.role = role
        self.text = text


def load(conversation, exchanges=None, before_id=None):
    """The last `exchanges` question/answer pairs, oldest first.

    Returns [] on any failure — a conversation whose history cannot be read
    must still be able to answer the current question, and this runs on the
    request path.

    `before_id` excludes messages from this id onward, which is what makes it
    safe to call after the current question has already been written to the
    conversation.
    """
    if conversation is None:
        return []
    exchanges = HISTORY_EXCHANGES if exchanges is None else exchanges
    if exchanges <= 0:
        return []
    try:
        from .models import Message

        rows = Message.objects.filter(conversation=conversation)
        if before_id is not None:
            rows = rows.filter(id__lt=before_id)
        # Ordered newest-first, sliced, then reversed — so the LIMIT happens in
        # the database rather than fetching a thousand-message conversation to
        # throw most of it away.
        recent = list(rows.order_by("-created_at", "-id")[: exchanges * 2])
        recent.reverse()
    except Exception:
        logger.exception("could not load conversation history")
        return []

    turns = []
    for row in recent:
        text = row.text if row.role == "user" else _clean_answer(row.text)
        if text and text.strip():
            turns.append(Turn(row.role, text.strip()))
    return turns


def digest(turns):
    """Recent turns as a short block for a prompt. Empty string when there are
    none, so a caller can interpolate it unconditionally."""
    if not turns:
        return ""
    lines = []
    for turn in turns:
        who = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{who}: {turn.text}")
    return "\n".join(lines)


def as_prompt_block(turns, heading="Earlier in this conversation"):
    """`digest` wrapped with a heading and a blank line, or "" when empty.

    Agents interpolate this directly. Returning "" rather than a heading with
    nothing under it matters: an empty "Earlier in this conversation:" section
    reads to a small model as "there was nothing before", which is worse than
    silence.
    """
    body = digest(turns)
    if not body:
        return ""
    return f"{heading}:\n{body}\n\n"


# --- resolution -------------------------------------------------------------

_RESOLVE_SYSTEM_PROMPT = """You rewrite a follow-up question so it can be understood on its own.

You are given the recent turns of a conversation and the user's latest question. Replace pronouns and implied references with what they actually refer to, using the conversation above.

Rules:
- Output ONLY the rewritten question. No explanation, no quotes, no preamble.
- Keep it short and in the user's own style. Do not add detail they did not ask for.
- Do NOT answer the question. You are rewriting it, not responding to it.
- If the question already stands on its own, output it completely unchanged.
- Never invent a subject that does not appear in the conversation above.

Examples:

Conversation:
User: How many departments are there?
Assistant: There are 8 departments.
Question: name them
Rewritten: Name the 8 departments.

Conversation:
User: How many faculty are in Engineering?
Assistant: There are 2,073 faculty in Engineering.
Question: what about Computer Science
Rewritten: How many faculty are in Computer Science?

Conversation:
User: Describe the Science department's development profile.
Assistant: Science has 1,803 faculty with an overall development index of 67.2.
Question: how does that compare to Medicine
Rewritten: How does the Science department's development profile compare to Medicine?

Conversation:
User: How many faculty are in Engineering?
Assistant: There are 2,073 faculty in Engineering.
Question: What is the tuition fee for Computer Science?
Rewritten: What is the tuition fee for Computer Science?
"""

RESOLVE_NUM_PREDICT = int(os.getenv("RESOLVE_NUM_PREDICT", "80"))


def _resolve_model():
    # The rewrite is a small, mechanical substitution — the 3B model handles it
    # and is roughly 2.5x faster than the 7B. Same model the router falls back
    # to, so on a default deployment it is already resident.
    #
    # MUST MATCH common.ollama._configured_models(), which is what the readiness
    # check and backend/scripts/required_models.sh both derive from. This was
    # the last model variable outside that set, and being outside it was worse
    # than the ROUTER_MODEL bug rather than a repeat of it: because is_ready()
    # never listed RESOLVE_MODEL, health stayed GREEN and a deployment that set
    # it explicitly would fail as a 404 from Ollama on the first follow-up
    # question. common/test_model_config.py now fails if a model variable is
    # missing from either side rather than only when the values disagree.
    #
    # Imported HERE, not at module level, matching resolve() below — and this
    # import is load-bearing rather than stylistic. Without it this function
    # raised NameError: resolve() imports `ollama` into ITS OWN local scope,
    # which a separate function cannot see. The try/except in resolve() catches
    # only LLMUnavailable, so the NameError escaped it and resolve() raised —
    # breaking its documented "NEVER RAISES" contract on the FIRST follow-up
    # question, where the whole point is to degrade to the unresolved question
    # rather than fail.
    from common import ollama

    return ollama.model_from_env(
        "RESOLVE_MODEL", ollama.model_from_env("ROUTER_MODEL", "qwen2.5:3b")
    )


def resolve(question, turns):
    """Rewrite `question` to stand alone. Returns the question unchanged when
    there is no history, when it does not look like a follow-up, or when
    anything at all goes wrong.

    NEVER RAISES. A failed rewrite must degrade to the previous behaviour —
    answering the question as asked — not to an error. The user gets what they
    would have got before this feature existed.
    """
    if not turns or not looks_like_followup(question):
        return question, False

    from common import ollama
    from common.exceptions import LLMUnavailable

    user_prompt = f"Conversation:\n{digest(turns)}\n\nQuestion: {question}\nRewritten:"
    try:
        raw = ollama.chat(
            _resolve_model(),
            messages=[
                {"role": "system", "content": _RESOLVE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": 0, "num_predict": RESOLVE_NUM_PREDICT},
            label="resolve_followup",
        )
    except LLMUnavailable as exc:
        logger.warning("could not resolve follow-up %r: %s", question[:60], exc)
        return question, False

    rewritten = _clean_rewrite(raw)
    if not rewritten:
        return question, False
    if rewritten.strip().lower() == (question or "").strip().lower():
        return question, False

    logger.info("resolved follow-up %r -> %r", question, rewritten)
    return rewritten, True


_REWRITE_PREFIX_RE = re.compile(r"^\s*(rewritten|question)\s*:\s*", re.IGNORECASE)

# Guards against the model answering instead of rewriting. Short is not enough:
# "There are 8 departments." is short and is an answer, not a question.
_ANSWER_SHAPED_RE = re.compile(
    r"^\s*(there (are|is|were|was)|the (college|records|answer)|it (is|has)|"
    r"i (couldn't|could not|cannot|can't))\b",
    re.IGNORECASE,
)


def _clean_rewrite(raw):
    """Strip decoration and reject output that is not a question.

    The failure this catches is the 3B model answering the question rather than
    rewriting it. Feeding "There are 8 departments." downstream as the question
    would send the SQL agent looking for a table of that sentence, and would
    poison the cache key with an answer.
    """
    text = " ".join((raw or "").split())
    text = _REWRITE_PREFIX_RE.sub("", text)
    text = text.strip().strip('"').strip("'").strip()
    if not text:
        return ""
    # One line only; the model occasionally adds commentary underneath.
    text = text.split("\n")[0].strip()
    if len(text) > 300:
        return ""
    if _ANSWER_SHAPED_RE.match(text):
        logger.warning("discarding a rewrite that looks like an answer: %r", text[:80])
        return ""
    return text
