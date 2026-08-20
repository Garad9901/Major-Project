# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from . import llm_client
from .untrusted import fence_passages, fence_sql_rows, new_fence

logger = logging.getLogger("synthesis_agent")


def _format_sql_section(sql_result, fence=None):
    """sql_result is duck-typed to match sql_agent.service.SqlAgentResult:
    .error, .generated_sql, .columns, .rows.

    Row values are fenced as untrusted: a course title or description is free
    text somebody typed into the registry, and it reaches the model verbatim.
    """
    return fence_sql_rows(sql_result, fence)


def _format_rag_section(rag_chunks, fence=None):
    """rag_chunks is duck-typed to match a list of rag_agent.service.RetrievedChunk:
    .table, .row_id, .score, .text.

    Fenced and provenance-labelled — see synthesis_agent/untrusted.py for the
    threat this addresses and, more importantly, for what it does not.
    """
    return fence_passages(rag_chunks, fence)


class _WebAsPassage:
    """Adapts a web_agent.WebPage to the shape fence_passages already handles.

    Deliberately reusing the existing fencing rather than writing a second
    version for web content: that code is covered by 13 tests and has already
    been hardened against a payload that defeated an earlier attempt. A parallel
    implementation would be a second thing to get right and a second thing to
    forget to update.

    Provenance shows the page LABEL and its URL, so the model — and the reader —
    can see the claim came from a published page rather than the database.
    """

    def __init__(self, page):
        self.table = f"web:{page.label}"
        self.row_id = page.url
        self.score = 1.0
        self.text = page.text


def _format_web_section(web_pages, fence=None):
    if not web_pages:
        return ""
    return fence_passages([_WebAsPassage(p) for p in web_pages], fence)


def _combined_context(rag_chunks, web_pages, fence=None):
    """RAG passages and fetched pages, each fenced, in one block.

    Kept as one section so llm_client's signature does not change; they are
    separately fenced and separately labelled inside it.
    """
    parts = [s for s in (_format_rag_section(rag_chunks, fence),
                         _format_web_section(web_pages, fence)) if s]
    return "\n\n".join(parts)


def synthesize_answer(question, route, sql_result=None, rag_chunks=None, web_pages=None,
                      history_block=""):
    # ONE fence per request. Every section the model sees is delimited by the
    # same nonce, and llm_client names that nonce in the reminder that sits
    # after the content — see synthesis_agent/untrusted.py, audit finding 13.
    fence = new_fence()
    sql_section = _format_sql_section(sql_result, fence)
    rag_section = _combined_context(rag_chunks, web_pages, fence)

    answer = llm_client.synthesize(
        question, route, sql_section, rag_section, history_block=history_block,
        fence=fence,
    )

    logger.info(
        "question=%r route=%s sql_rows=%d rag_chunks=%d",
        question, route,
        len(sql_result.rows) if sql_result and sql_result.rows else 0,
        len(rag_chunks) if rag_chunks else 0,
    )
    return answer


def synthesize_answer_stream(question, route, sql_result=None, rag_chunks=None,
                             web_pages=None, history_block=""):
    """Streaming variant of synthesize_answer: yields the answer in pieces as
    the model generates them."""
    fence = new_fence()
    sql_section = _format_sql_section(sql_result, fence)
    rag_section = _combined_context(rag_chunks, web_pages, fence)

    logger.info(
        "streaming question=%r route=%s sql_rows=%d rag_chunks=%d web_pages=%d",
        question, route,
        len(sql_result.rows) if sql_result and sql_result.rows else 0,
        len(rag_chunks) if rag_chunks else 0,
        len(web_pages) if web_pages else 0,
    )
    yield from llm_client.synthesize_stream(
        question, route, sql_section, rag_section, history_block=history_block,
        fence=fence,
    )
