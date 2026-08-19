# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The fixed set of URLs this system may fetch, and how one is chosen.

THE CENTRAL RULE
The language model never supplies a URL. It is not asked to. It cannot be
prompted into asking for one, because nothing in this module accepts a URL as
input — selection happens by deterministic keyword matching against `topics` in
the `web_sources` section of config/institution.json.

That is a deliberate design choice rather than a filter. A "generate a URL, then
validate it" design is only as good as the validator, and a validator that must
reason about URL parsing (userinfo, IDN homographs, redirects, `..` traversal,
DNS rebinding) is exactly the kind of thing that looks correct and is not. Here
there is nothing to validate: the request URL is a string copied verbatim out of
a file on disk, chosen by index.

Consequences worth stating:
  * The system can never fetch a page nobody put in the file.
  * A prompt injection can never cause a fetch, because injected text is not
    consulted for URL selection.
  * Adding a source is a file edit and a restart — deliberate and reviewable.
"""

import json
import logging
import os
import re
import threading
from urllib.parse import urlparse

logger = logging.getLogger("web_agent")

# WHERE THE LIST LIVES, AND WHY IT MOVED.
#
# It used to be web_agent/urls_allowlist.json, one of three separate places a
# new college had to edit (the others being frontend/src/institute.js and .env).
# It is now a section of config/institution.json — the single file a college
# fills in — so that deploying for a new institution is one file, not a hunt.
#
# NOTHING ABOUT THE SECURITY MODEL CHANGED. The same _validate() runs on the
# same fields, the model still never sees this list and still never supplies a
# URL, and selection is still deterministic keyword matching. Only the bytes'
# location moved.
#
# The legacy path is still read when the new one has no web_sources section, so
# an existing deployment keeps working across the upgrade without an edit.
_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "institution.json")
)
_LEGACY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urls_allowlist.json")

ALLOWLIST_PATH = os.getenv("WEB_AGENT_ALLOWLIST", os.getenv("INSTITUTION_CONFIG", _CONFIG_PATH))

# Only these schemes are ever fetched. file:, ftp:, gopher: and data: are all
# ways to turn a fetcher into something else entirely.
ALLOWED_SCHEMES = frozenset({"http", "https"})

_WORD_RE = re.compile(r"[a-z0-9]+")

_lock = threading.Lock()
_entries = None


class AllowlistError(Exception):
    pass


def _validate(entry, seen_ids):
    """Reject a malformed entry at LOAD time rather than at fetch time.

    Loudly, because a silently-skipped entry looks identical to a page that
    simply had nothing useful on it.
    """
    for field in ("id", "url", "label"):
        if not entry.get(field):
            raise AllowlistError(f"allowlist entry missing '{field}': {entry!r}")

    if entry["id"] in seen_ids:
        raise AllowlistError(f"duplicate allowlist id: {entry['id']!r}")

    parsed = urlparse(entry["url"])
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise AllowlistError(
            f"allowlist entry {entry['id']!r} has scheme {parsed.scheme!r}; "
            f"only {sorted(ALLOWED_SCHEMES)} are permitted"
        )
    if not parsed.hostname:
        raise AllowlistError(f"allowlist entry {entry['id']!r} has no hostname")
    # Credentials in a URL would be logged and are never appropriate here.
    if parsed.username or parsed.password:
        raise AllowlistError(f"allowlist entry {entry['id']!r} embeds credentials")


def load(force=False):
    """Parse and validate the allowlist once, then cache it in memory."""
    global _entries
    with _lock:
        if _entries is not None and not force:
            return _entries

        raw, source = _read_source()
        if raw is None:
            logger.warning(
                "no allowlist at %s (or %s) — the web agent is disabled",
                ALLOWLIST_PATH, _LEGACY_PATH,
            )
            _entries = []
            return _entries

        # Accepts both shapes: {"web_sources": {"urls": [...]}} in the unified
        # config, and the legacy top-level {"urls": [...]}.
        section = raw.get("web_sources")
        entries = (section or {}).get("urls") if isinstance(section, dict) else None
        if entries is None:
            entries = raw.get("urls", [])

        seen = set()
        out = []
        for entry in entries:
            # Documentation keys are ignored rather than validated; the config
            # file carries _comment blocks for whoever opens it.
            if not isinstance(entry, dict):
                raise AllowlistError(f"allowlist entry must be an object, got {entry!r}")
            _validate(entry, seen)
            seen.add(entry["id"])
            if entry.get("enabled", True):
                out.append({
                    "id": entry["id"],
                    "url": entry["url"],
                    "label": entry["label"],
                    "topics": [t.lower() for t in entry.get("topics", [])],
                })

        _entries = out
        logger.info(
            "web allowlist loaded from %s: %d enabled entr%s (%s)",
            source, len(out), "y" if len(out) == 1 else "ies",
            ", ".join(e["id"] for e in out) or "none",
        )
        return _entries


def _read_source():
    """Return (parsed_json, path) from the configured file, else the legacy one.

    Returns (None, None) when neither exists. A JSON error still RAISES rather
    than falling back: a typo must not silently disable the feature, because
    "no results" and "misconfigured" would then look identical.
    """
    for path in (ALLOWLIST_PATH, _LEGACY_PATH):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh), path
        except json.JSONDecodeError as exc:
            raise AllowlistError(f"{path} is not valid JSON: {exc}") from exc
    return None, None


def is_allowed(url):
    """Exact-match membership test.

    Exact, not prefix or domain matching. 'starts with https://college.edu' is
    satisfied by 'https://college.edu.attacker.test/', and 'host ends with
    college.edu' is satisfied by 'notcollege.edu'. Comparing the whole string
    against a known set has no such edge cases.
    """
    return any(e["url"] == url for e in load())


def entry_for_url(url):
    for e in load():
        if e["url"] == url:
            return e
    return None


def select_for_question(question, limit=2):
    """Choose which allowlisted pages (if any) a question needs.

    Scored by how many of an entry's topic phrases appear in the question.
    Multi-word topics are matched as phrases, which is what makes "academic
    calendar" score for the calendar page without every question containing the
    word "academic" doing so.

    Returns entries, never URLs built from the question text.
    """
    q = " ".join((question or "").lower().split())
    q_words = set(_WORD_RE.findall(q))
    if not q:
        return []

    scored = []
    for e in load():
        score = 0
        for topic in e["topics"]:
            if " " in topic:
                if topic in q:
                    score += 2          # phrase match is a strong signal
            elif topic in q_words:
                score += 1
        if score:
            scored.append((score, e))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [e for _, e in scored[:limit]]


def describe():
    """Human-readable inventory, for logs and the verification script."""
    return [{"id": e["id"], "url": e["url"], "label": e["label"]} for e in load()]
