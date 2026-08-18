# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import re

from . import fast_router, llm_client


def embed_text(text):
    """Imported lazily so router_agent does not import rag_agent at module load
    (rag_agent pulls in the Qdrant client, which this module does not need
    unless the embedding tier is actually reached)."""
    from rag_agent.embedder import embed_text as _embed
    return _embed(text)

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


def classify(question, history_block="", previous_route=None):
    """Decide the route. Does not call any downstream agent.

    `history_block` is recent conversation as text (see
    orchestrator/conversation.as_prompt_block) and is used only by the LLM
    tier. `previous_route` is what the last question in this conversation
    resolved to, and is used as the fallback for a follow-up the tiers cannot
    classify — see the note at the bottom of this function.

    THREE TIERS, and the LLM is the last one — see router_agent/fast_router.py.
    Measured before this change: the LLM router cost 5.2-9.1s warm (and 60s
    cold) to emit about twenty tokens of JSON, because the prompt it reads is
    ~1,200 tokens of worked examples and it was reading them with a 7B model.
    The first two tiers answer the overwhelming majority of questions in
    microseconds or tens of milliseconds.

    A misroute is cheap and recoverable: it yields a worse answer, never an
    unsafe one. Routing grants no capability — the SQL guard, the table
    allowlist and the read-only role are all downstream of this and unaffected
    by what it returns.
    """
    if fast_router.FAST_ROUTER_ENABLED:
        route, reason, confident = fast_router.classify_by_rules(question)
        if confident:
            logger.info("question=%r route=%s tier=rules reason=%s", question, route, reason)
            return RouteResult(question, route=route, reason=reason)

        route, reason, confident = fast_router.classify_by_embedding(question, embed_text)
        if confident:
            logger.info("question=%r route=%s tier=embedding reason=%s", question, route, reason)
            return RouteResult(question, route=route, reason=reason)

        logger.info("router: tiers 1-2 unconfident for %r, falling back to the LLM", question[:60])

    raw_output = llm_client.classify_question(question, history_block=history_block)
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
        # INHERIT RATHER THAN DEFAULT, when this is a follow-up.
        #
        # The generic fallback is BOTH, which for "name them" means running a
        # retrieval search for the word "them" alongside the SQL. If the
        # previous turn in this conversation resolved to a route, that route is
        # a far better guess: a follow-up to a records question is almost
        # always another records question.
        if previous_route in VALID_ROUTES:
            logger.info(
                "router: unparseable route for follow-up %r, inheriting %s from the "
                "previous turn", question[:60], previous_route,
            )
            return RouteResult(
                question, route=previous_route,
                reason=f"follow-up; inherited {previous_route} from the previous question",
                raw_output=raw_output,
            )
        return RouteResult(question, raw_output=raw_output, error=f"model returned invalid route: {route!r}")

    logger.info("question=%r route=%s reason=%s", question, route, reason)
    return RouteResult(question, route=route, reason=reason, raw_output=raw_output)
