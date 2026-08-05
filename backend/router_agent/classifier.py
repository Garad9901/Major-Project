# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import re

from . import llm_client

logger = logging.getLogger("router_agent")

# WEB is the fourth path: content that lives on a published college page rather
# than in the database or the search index — calendars, notices, circulars.
#
# It is a route, not a capability grant. Choosing WEB only decides that the web
# agent runs; WHICH page it fetches is settled by keyword matching against
# web_agent/urls_allowlist.json, never by the model. See web_agent/allowlist.py.
VALID_ROUTES = {"SQL", "RAG", "BOTH", "WEB"}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class RouteResult:
    def __init__(self, question, route=None, reason=None, raw_output=None, error=None):
        self.question = question
        self.route = route
        self.reason = reason
        self.raw_output = raw_output
        self.error = error

    @property
    def ok(self):
        return self.error is None


def classify(question):
    """Classifies a question as SQL / RAG / BOTH. Does not call either agent
    — this is routing decision-making only, kept deliberately separate so it
    can be reviewed on its own before anything gets wired to it."""
    raw_output = llm_client.classify_question(question)
    text = _CODE_FENCE_RE.sub("", raw_output).strip()

    try:
        parsed = json.loads(text)
        route = str(parsed.get("route", "")).strip().upper()
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("failed to parse router output question=%r raw=%r error=%s", question, raw_output, exc)
        return RouteResult(question, raw_output=raw_output, error=f"could not parse model output as JSON: {exc}")

    if route not in VALID_ROUTES:
        logger.warning("router returned invalid route question=%r route=%r raw=%r", question, route, raw_output)
        return RouteResult(question, raw_output=raw_output, error=f"model returned invalid route: {route!r}")

    logger.info("question=%r route=%s reason=%s", question, route, reason)
    return RouteResult(question, route=route, reason=reason, raw_output=raw_output)
