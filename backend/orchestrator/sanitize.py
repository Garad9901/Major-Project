# Copyright (c) 2026 Yash Garad. All rights reserved.

import re

# Defense-in-depth for the chat box. The real structural guarantees are
# elsewhere — the SQL guard rejects anything touching non-allowlisted tables
# or attempting writes, and the RAG agent is read-only — so a prompt-injection
# attempt can't reach the database destructively. This layer caps abuse
# (huge prompts burning LLM compute) and neutralizes control characters that
# could forge fake lines in the audit log or agent logs.

MAX_QUESTION_LENGTH = 500

# Strip C0/C1 control characters except normal whitespace (tab/newline are
# collapsed to spaces below anyway). Prevents log-line forging and terminal
# escape tricks in anything that echoes the question.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")

# Phrases we record (not block) — blocking on wording is brittle and easy to
# evade, so we surface them in the audit trail rather than reject, and let the
# structural defenses do the actual protecting.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |the )?(previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"disregard (all |the )?(previous|prior|above)", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"drop\s+table", re.I),
    re.compile(r"delete\s+from", re.I),
]


class QuestionRejected(Exception):
    """Raised when input can't be made into a usable question. `code` is one of
    'empty' or 'too_long' so the caller can respond politely per case."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def sanitize_question(raw):
    """Return (clean_text, flags). Raises QuestionRejected for empty or
    over-length input. `flags` lists any injection-style patterns seen — for
    the audit log, not for blocking."""
    text = _CONTROL_CHARS.sub("", str(raw or ""))
    text = _WHITESPACE.sub(" ", text).strip()

    if not text:
        raise QuestionRejected("the question is empty", code="empty")
    if len(text) > MAX_QUESTION_LENGTH:
        raise QuestionRejected(
            f"the question is too long ({len(text)} chars; max {MAX_QUESTION_LENGTH})",
            code="too_long",
        )

    flags = [p.pattern for p in _INJECTION_PATTERNS if p.search(text)]
    return text, flags
