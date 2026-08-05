# Copyright (c) 2026 Yash Garad. All rights reserved.

"""HTML -> readable text, and stripping instruction-shaped text from it.

NO NEW DEPENDENCY. BeautifulSoup would be nicer to write, but html.parser is in
the standard library and this parser only needs to do one narrow thing: drop
markup and keep visible text. A new package in the image is a new thing to patch.

WHY SANITISING IS SEPARATE FROM FENCING
Retrieved database text is already fenced as untrusted before it reaches the
model (synthesis_agent/untrusted.py), and fetched pages get the same treatment.
Fencing is the structural control and it stays. This module is an ADDITIONAL,
earlier pass, because web content differs from database content in one respect:
nobody at the college wrote it or reviewed it. A page can change between one
fetch and the next without anyone noticing.

So instruction-shaped lines are removed from the text ENTIRELY rather than
merely being fenced. Two layers, in order:

    1. strip anything that reads like an instruction to an AI   (here)
    2. fence whatever survives as untrusted data                (synthesis)

Layer 1 is heuristic and WILL miss novel phrasings — it is defence in depth, not
a boundary. Layer 2 is the boundary. Anything relying on layer 1 alone would be
relying on a blocklist, which is the weaker of the two by a wide margin.
"""

import logging
import re
from html import unescape
from html.parser import HTMLParser

logger = logging.getLogger("web_agent")

# Elements whose CONTENT is never visible text. Depth-counted, so nested
# occurrences are handled.
#
# VOID ELEMENTS MUST NOT BE IN THIS SET. `meta` and `link` have a start tag and
# no end tag, so counting them would increment the skip depth forever and
# silently swallow the entire rest of the document. That is not hypothetical:
# they were in this set, and every page containing `<meta charset=...>` — which
# is essentially all of them — extracted to an empty string. The fetch
# succeeded, the audit log said "ok", and the agent contributed nothing.
#
# They need no handling at all: void elements carry no text to skip.
_SKIP_ELEMENTS = frozenset({
    "script", "style", "noscript", "template", "svg", "canvas",
    "head", "title", "iframe", "object", "embed",
})

# Void elements: no end tag ever arrives, so they must never affect depth.
_VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

# Elements after which a line break belongs, so paragraphs do not run together.
_BLOCK_ELEMENTS = frozenset({
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "blockquote", "pre", "table",
})

# CONTENT HIDDEN FROM HUMAN READERS IS DROPPED ENTIRELY.
#
# WHY THIS IS THE IMPORTANT CONTROL IN THIS MODULE
# The injection patterns below are a blocklist, and the docstring is honest that
# a blocklist will miss novel phrasings. This check is not a blocklist. It keys
# on the one property that every practical web prompt-injection shares and that
# no legitimate content shares: the text is invisible to the person the page was
# written for, while remaining fully visible to a program that reads the markup.
#
# An audit against a simulated hostile calendar page found the sanitiser removing
# 1 of 6 payloads. Five survived, and every one of them was delivered this way —
# a display:none div, a font-size:0 paragraph, an aria-hidden span. A page can be
# entirely legitimate to every human who visits it and still carry instructions
# aimed only at this system, which is precisely the scenario that makes fetching
# third-party pages risky.
#
# Nothing legitimate is lost: text a sighted visitor cannot read is not
# information the college is publishing. (Screen-reader-only text — the
# `.sr-only` clip pattern — is deliberately included in the drop, because it is
# indistinguishable from the attack and never carries facts the visible page
# omits.)
_HIDDEN_STYLE_RE = re.compile(
    r"(?:^|;)\s*(?:"
    r"display\s*:\s*none"
    r"|visibility\s*:\s*hidden"
    r"|opacity\s*:\s*0(?:\.0+)?(?:\s|;|$)"
    r"|font-size\s*:\s*0(?:px|pt|em|rem|%)?(?:\s|;|$)"
    r"|text-indent\s*:\s*-\s*\d"
    r"|(?:left|top)\s*:\s*-\s*\d{4,}"
    r")",
    re.IGNORECASE,
)


def _is_hidden(attrs):
    """True when this element's own attributes hide it from a human reader."""
    for name, value in attrs:
        if value is None:
            # Bare boolean attribute, e.g. <div hidden>
            if name.lower() == "hidden":
                return True
            continue
        lname = name.lower()
        if lname == "hidden":
            return True
        if lname == "aria-hidden" and value.strip().lower() == "true":
            return True
        if lname == "style" and _HIDDEN_STYLE_RE.search(value):
            return True
    return False


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._skip_depth = 0
        # Names of currently-open non-void elements. Used to unwind correctly
        # when a page leaves inner tags unclosed, which is extremely common.
        self._stack = []
        # Stack length at which the outermost hidden element opened, or None.
        # Tracked by depth rather than by a counter so that a hidden subtree
        # containing further hidden elements still un-hides exactly once.
        self._hidden_at = None

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_ELEMENTS:
            # Never affects depth. A <br> still deserves a line break.
            if tag in _BLOCK_ELEMENTS:
                self._parts.append("\n")
            return
        self._stack.append(tag)
        if self._hidden_at is None and _is_hidden(attrs):
            self._hidden_at = len(self._stack)
        if tag in _SKIP_ELEMENTS:
            self._skip_depth += 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        # Explicitly self-closed (<br/>). Base class would call start then end,
        # which for a skip element would balance — but being explicit here keeps
        # the depth logic in one place. A self-closed element encloses nothing,
        # so it cannot hide anything and must not touch the stack.
        if tag in _VOID_ELEMENTS:
            if tag in _BLOCK_ELEMENTS:
                self._parts.append("\n")
            return
        if tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            return
        if tag in _SKIP_ELEMENTS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")
        if tag in self._stack:
            # Unwind to the matching open tag, discarding any inner tags the
            # page never closed. Without this the depth drifts upward on real
            # pages and the hidden region would never be exited.
            while self._stack:
                popped = self._stack.pop()
                if popped == tag:
                    break
        if self._hidden_at is not None and len(self._stack) < self._hidden_at:
            self._hidden_at = None

    def handle_data(self, data):
        if self._skip_depth == 0 and self._hidden_at is None:
            self._parts.append(data)

    def text(self):
        return "".join(self._parts)


# Lines matching any of these are dropped. Case-insensitive, and tolerant of
# padding characters used to slip past naive matching ("i g n o r e" is not
# covered — again, this is depth, not a boundary).
#
# The determiner/possessive alternations below (`the|your|its|all`) and the
# optional-colon forms are not padding: each corresponds to a payload that a
# real audit watched walk straight through the previous version of this list.
# Those misses are named individually so a future edit does not "simplify" them
# back out.
_INJECTION_PATTERNS = [
    # "ignore the above and instead ..." previously escaped: `above` had to be
    # followed by instructions/prompts/rules, and here it is followed by "and".
    r"ignore\s+(all\s+|the\s+)?(previous|prior|earlier|above)\b",
    # "disregard YOUR previous instructions" previously escaped: `your` and
    # `its` were absent from this alternation.
    r"disregard\s+(all\s+|the\s+|your\s+|its\s+)?(previous|prior|earlier|above|the|your)\s+",
    r"forget\s+(everything|all|your)\s+(you|instructions?|rules?|above)",
    # "You are now DAN." previously escaped: a/an/in were required to follow.
    # NOT widened to a bare "you are now" — a college page saying "you are now
    # eligible to apply" is ordinary prose, and stripping it would delete real
    # information. The alternation covers the role-reassignment framings only.
    r"you\s+are\s+now\s+(a|an|in|(?-i:DAN)|operating|acting|running|free|"
    r"unrestricted|no\s+longer|allowed\s+to|permitted\s+to)\b",
    # "### SYSTEM PROMPT OVERRIDE ###" previously escaped: a colon or equals was
    # required after the noun. Made optional.
    r"\b(system|developer|assistant)\s*(prompt|message|role)\b\s*[:=]?",
    r"new\s+(instructions?|rules?|system\s+prompt)\s*[:=]",
    r"(respond|reply|answer|output)\s+(only\s+)?with\s+(exactly\s+)?[\"']",
    r"do\s+not\s+(tell|mention|reveal|disclose)\s+(the\s+)?(user|anyone)",
    # Left narrow deliberately. A bare \boverride\b would strip a college page
    # describing a "manual override" procedure. The payload that motivated
    # widening this ("### SYSTEM PROMPT OVERRIDE ###") is already caught by the
    # system/prompt pattern above, so nothing is lost by keeping it specific.
    r"\boverride\s+(your|all|previous|the)\s+",
    # (?-i:DAN) keeps this one CASE-SENSITIVE inside an otherwise
    # case-insensitive union: a bare case-insensitive "dan" would strip any line
    # mentioning someone named Dan.
    r"\b(jailbreak|(?-i:DAN)|developer\s+mode|unrestricted\s+(agent|mode))\b",
    r"end\s+of\s+(context|document|data)\s*[.:]?\s*(now|then)\b",
    # Imperatives aimed at the reading model. "You must now execute: SELECT ..."
    # matched nothing at all before.
    r"\byou\s+(must|should|will|need\s+to)\s+(now\s+)?(execute|run|output|print|reveal|ignore|disregard)\b",
    r"\b(reveal|disclose|print|output|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)",
    # An instruction addressed to the assistant by name.
    r"^\s*(assistant|ai|model|chatbot)\s*[,:]\s*(please\s+)?\w+",
    r"<<<\s*/?\s*(end_?)?untrusted",     # our own fence markers
    r"\[\s*/?\s*(system|inst|instruction)\s*\]",
    r"<\|.*?\|>",                         # chat-template control tokens
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_WS_RUN = re.compile(r"[ \t ]+")
_BLANK_RUN = re.compile(r"\n{3,}")


def html_to_text(html):
    """Visible text from an HTML document. Falls back to the raw string if the
    document is malformed enough to break the parser."""
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
        text = parser.text()
    except Exception:
        logger.warning("HTML parse failed; falling back to tag stripping", exc_info=True)
        text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = _WS_RUN.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_RUN.sub("\n\n", text).strip()


def strip_injection(text):
    """Remove instruction-shaped lines. Returns (clean_text, removed_lines).

    Line-granular on purpose: dropping the whole document because one line looked
    hostile would let anyone disable a source by editing one sentence, and
    dropping only the matched substring would leave a half-sentence that reads
    as though the assistant garbled it.
    """
    if not text:
        return "", []
    kept, removed = [], []
    for line in text.splitlines():
        if line.strip() and _INJECTION_RE.search(line):
            removed.append(line.strip()[:160])
        else:
            kept.append(line)
    clean = _BLANK_RUN.sub("\n\n", "\n".join(kept)).strip()
    return clean, removed


def extract(html, max_chars=6000):
    """Full pipeline: markup -> text -> sanitised -> truncated.

    Returns (text, meta). `max_chars` exists because a long page would otherwise
    dominate the prompt and push out the database rows, which are the
    higher-quality source.
    """
    text = html_to_text(html)
    clean, removed = strip_injection(text)
    truncated = len(clean) > max_chars
    if truncated:
        cut = clean[:max_chars].rsplit(" ", 1)[0]
        clean = cut + "\n\n[content truncated]"
    if removed:
        logger.warning(
            "stripped %d instruction-like line(s) from fetched content: %r",
            len(removed), removed[:3],
        )
    return clean, {
        "chars": len(clean),
        "truncated": truncated,
        "injection_lines_removed": len(removed),
        "injection_samples": removed[:3],
    }
