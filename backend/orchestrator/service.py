# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
from concurrent.futures import ThreadPoolExecutor

from common.exceptions import (
    DatabaseUnavailable,
    ServiceUnavailable,
    VectorStoreUnavailable,
)
from rag_agent.embedder import embed_text
from rag_agent.service import retrieve
from router_agent.classifier import classify
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer, synthesize_answer_stream
from web_agent.service import fetch_for_question

from . import cache, verification
from .concurrency import llm_slot
from .profiling import Profile

logger = logging.getLogger("orchestrator")

DEFAULT_ROUTE_ON_ERROR = "BOTH"
RAG_TOP_K = 5

# User-facing degradation notes appended to an answer when one source is down
# but we could still answer from the other.
DB_DOWN_NOTE = (
    "Note: live records lookup is temporarily unavailable, so this answer is "
    "based on descriptive information only."
)
RAG_DOWN_NOTE = (
    "Note: descriptive search is temporarily unavailable, so this answer is "
    "based on the structured records only."
)
WEB_EMPTY_NOTE = (
    "Note: no official college page matching this question could be read, so "
    "this answer comes from the records held in the database."
)
RAG_DOWN_SQL_FALLBACK_NOTE = (
    "Note: descriptive search is temporarily unavailable; answering from the "
    "structured records instead."
)


def _resolve_route(question):
    # classify() can raise LLMUnavailable (Ollama down) — we let that propagate,
    # since if the LLM is down synthesis can't run either. A *parse* failure
    # (route_result.error) is different: fall back to BOTH and carry on.
    route_result = classify(question)
    if route_result.error:
        logger.warning(
            "router failed question=%r error=%s — falling back to %s",
            question, route_result.error, DEFAULT_ROUTE_ON_ERROR,
        )
        return DEFAULT_ROUTE_ON_ERROR, f"router error, defaulted to {DEFAULT_ROUTE_ON_ERROR}"
    return route_result.route, route_result.reason


def _run_sql(question, profile):
    # Timed INSIDE the worker thread, not around pool.submit(), so the recorded
    # interval is when the work actually ran rather than when it was queued.
    # That distinction is the whole point when proving the two branches overlap.
    with profile.stage("sql"):
        return sql_ask(question, execute=True)


def _run_rag(question, profile):
    with profile.stage("rag"):
        return retrieve(question, top_k=RAG_TOP_K)


def _gather_sources(question, route, profile=None):
    """Fetch SQL and/or RAG data for the route, degrading gracefully when ONE
    source is down. Returns (sql_result, rag_chunks, effective_route, notes).

    Raises a ServiceUnavailable only when no usable source remains (e.g. a
    SQL-only question with the database down, or a descriptive question with
    the vector store down and no useful SQL fallback). LLMUnavailable from the
    embed/generate steps propagates untouched — if the LLM is down, the whole
    request can't be served anyway.
    """
    needs_sql = route in ("SQL", "BOTH")
    needs_rag = route in ("RAG", "BOTH")
    sql_result = None
    rag_chunks = None
    notes = []
    profile = profile or Profile()

    if route == "WEB":
        # The web agent NEVER raises for an unreachable page: it logs the
        # failure and returns fewer pages. So an empty list here means "no
        # allowlisted page matched, or none could be read", and the honest
        # fallback is the database rather than an error.
        with profile.stage("web_fetch"):
            pages = fetch_for_question(question)
        if pages:
            return None, None, "WEB", notes, pages
        logger.info("WEB route produced no pages; falling back to SQL for %r", question[:60])
        notes.append(WEB_EMPTY_NOTE)
        sql_result = _run_sql(question, profile)
        return sql_result, None, "SQL", notes, []

    if needs_sql and needs_rag:
        # Independent I/O — run concurrently, but tolerate either one failing.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_sql = pool.submit(_run_sql, question, profile)
            f_rag = pool.submit(_run_rag, question, profile)
            try:
                sql_result = f_sql.result()
            except DatabaseUnavailable as exc:
                logger.warning("SQL source down (route=BOTH), degrading to RAG-only: %s", exc)
                notes.append(DB_DOWN_NOTE)
            try:
                rag_chunks = f_rag.result()
            except VectorStoreUnavailable as exc:
                logger.warning("RAG source down (route=BOTH), degrading to SQL-only: %s", exc)
                notes.append(RAG_DOWN_NOTE)

        if sql_result is None and rag_chunks is None:
            raise ServiceUnavailable()  # both sources down — nothing to answer from
        effective = "BOTH"
        if sql_result is not None and rag_chunks is None:
            effective = "SQL"
        elif rag_chunks is not None and sql_result is None:
            effective = "RAG"
        return sql_result, rag_chunks, effective, notes, []

    if needs_sql:  # SQL-only — a DB outage here is fatal (no source to fall back on)
        sql_result = _run_sql(question, profile)
        return sql_result, None, "SQL", notes, []

    # RAG-only
    try:
        rag_chunks = _run_rag(question, profile)
    except VectorStoreUnavailable:
        # Try SQL as a fallback; use it only if it actually found something.
        logger.warning("RAG source down (route=RAG), attempting SQL fallback")
        fallback = _run_sql(question, profile)
        if fallback.rows:
            notes.append(RAG_DOWN_SQL_FALLBACK_NOTE)
            return fallback, None, "SQL", notes, []
        raise  # nothing useful from SQL — surface the clean "descriptive search down" message
    return None, rag_chunks, "RAG", notes, []


def answer_question(question):
    """Full pipeline, blocking. Returns a dict with the final answer plus
    intermediate metadata. Degrades gracefully; raises ServiceUnavailable only
    when nothing can be answered."""
    # One slot for the whole pipeline. Raises AssistantBusy if the queue wait
    # expires, which the API layer turns into a "busy, try again" message.
    with llm_slot(label=f"blocking q={question[:40]!r}"):
        route, reason = _resolve_route(question)
        sql_result, rag_chunks, effective_route, notes, web_pages = _gather_sources(question, route)
        answer = synthesize_answer(
            question, effective_route, sql_result=sql_result, rag_chunks=rag_chunks,
            web_pages=web_pages,
        )
        # Inside the slot: verification is more LLM work, so it must not run
        # concurrently with someone else's answer.
        answer, trailing, vmeta = verification.verify(
            question, effective_route, answer,
            sql_result=sql_result, rag_chunks=rag_chunks, web_pages=web_pages,
        )
    if trailing:
        answer = answer + trailing
    if notes:
        answer = answer + "\n\n" + "\n".join(notes)

    logger.info("answered question=%r route=%s degraded=%s", question, effective_route, bool(notes))
    return {
        "question": question,
        "route": effective_route,
        "route_reason": reason,
        "answer": answer,
        "degraded": bool(notes),
        "notes": notes,
        "sql": _sql_meta(sql_result),
        "rag": _rag_meta(rag_chunks),
        "web": _web_meta(web_pages),
        "verification": vmeta,
    }


def answer_question_stream(question, bypass_cache=False):
    """Full pipeline, streaming. Yields ('meta', {...}), then ('token', str)
    per piece, then ('done', {...}). Degradation notes (if any) are streamed
    as trailing tokens so the user sees why the answer is limited. Raises
    ServiceUnavailable when nothing can be answered, or AssistantBusy when no
    LLM slot frees up in time — the API layer turns both into clean user-facing
    messages.

    NOTE ON SLOT LIFETIME: the slot is held across every `yield`, i.e. for as
    long as the client is still reading the stream. That is intended — the model
    is genuinely occupied for that whole period. The `finally` inside llm_slot()
    releases it when this generator is closed, including when Django closes it
    because the client disconnected mid-answer.
    """
    # REGENERATE MUST NOT BE ANSWERED FROM THE CACHE.
    #
    # Found while testing Prompt 27: an intermittently wrong answer ("There are
    # 0 faculty members in the Medicine department" — the model had queried the
    # 7-row staff directory instead of the 13,000-row survey) was stored by the
    # semantic cache and then replayed to every subsequent user, identical every
    # time, for the rest of the process lifetime. Verification could not catch
    # it: the answer faithfully reported what its own (wrong) query returned.
    #
    # Regenerate is the one control a user has when an answer looks wrong. If it
    # returned the same cached text it would be useless exactly when it matters,
    # so it skips the lookup — and the fresh answer is still STORED, which
    # overwrites the bad entry and repairs it for everyone else.
    if bypass_cache:
        logger.info("cache bypassed (regenerate) for %r", question[:60])
        yield from _generate_stream(question)
        return

    # CACHE CHECK BEFORE THE SLOT, DELIBERATELY.
    #
    # Doing it inside llm_slot() would make every cached answer queue behind
    # whoever is currently generating — with LLM_MAX_CONCURRENCY=1 and fifty
    # simultaneous users, forty-nine of them would be told the assistant is busy
    # and then be handed an answer that was sitting in memory the whole time.
    # Out here, a hit costs no slot and blocks nobody.
    hit = cache.lookup(question, embed_text)

    # COALESCE. A plain cache does nothing for simultaneous identical questions:
    # they all look up before the first answer exists, and all miss. If someone
    # is already generating this exact question, wait for their result rather
    # than queuing for a second LLM slot to compute the same thing.
    if hit is None:
        if cache.begin(question):
            leader = True
        else:
            leader = False
            waited = cache.await_result(question)
            if waited and waited[0]:
                hit = (waited[0], waited[1], "coalesced")
            else:
                # Leader failed or timed out — fall back to doing it ourselves.
                leader = cache.begin(question)
    else:
        leader = False

    if hit is not None:
        answer, cached_route, how = hit
        yield "meta", {
            "question": question,
            "route": cached_route,
            "route_reason": "served from cache",
            "degraded": False,
            "cached": how,
            "sql": None,
            "rag": None,
        }
        yield "token", answer
        yield "done", {"answer": answer, "verification": {"verification": "cached"}}
        return

    try:
        yield from _generate_stream(question)
    finally:
        # Always release waiters, including on error or client disconnect.
        # _generate_stream publishes the real result via cache.finish() on
        # success; this is the safety net that stops followers hanging.
        if leader:
            cache.finish(question)


def _generate_stream(question):
    """The real pipeline. Separated so the coalescing wrapper above stays
    readable and so `finally` cleanup is unambiguous."""
    profile = Profile()
    with llm_slot(label=f"stream q={question[:40]!r}"):
        profile.mark("slot_acquired")
        with profile.stage("router"):
            route, reason = _resolve_route(question)

        # Emitted BEFORE the data stages, which are the slow part. The SPA can
        # say "looking up records" the moment routing is decided instead of
        # showing nothing until the first synthesis token, which on this
        # hardware is tens of seconds later. See views.py for the SSE event.
        yield "stage", {"stage": "routing_done", "route": route, "reason": reason}

        sql_result, rag_chunks, effective_route, notes, web_pages = _gather_sources(
            question, route, profile
        )

        yield "meta", {
            "question": question,
            "route": effective_route,
            "route_reason": reason,
            "degraded": bool(notes),
            "sql": _sql_meta(sql_result),
            "rag": _rag_meta(rag_chunks),
            "web": _web_meta(web_pages),
        }
        yield "stage", {"stage": "sources_ready", "route": effective_route}

        pieces = []
        first_token_seen = False
        synthesis_started = profile.total_ms
        for piece in synthesize_answer_stream(
            question, effective_route, sql_result=sql_result, rag_chunks=rag_chunks,
            web_pages=web_pages,
        ):
            if not first_token_seen:
                first_token_seen = True
                profile.mark("synthesis_first_token")
            pieces.append(piece)
            yield "token", piece
        profile.stages.append({
            "name": "synthesis",
            "start_ms": synthesis_started,
            "end_ms": profile.total_ms,
            "ms": round(profile.total_ms - synthesis_started, 1),
            "thread": "main",
            "error": None,
        })

        # VERIFICATION runs only now, because it needs a COMPLETE answer.
        #
        # The user has already read the answer at this point, which is the
        # deliberate trade-off: buffering it to verify first would add the full
        # verification delay (~9.5s measured) BEFORE the first word appeared,
        # and destroy streaming entirely. Instead the correction arrives a few
        # seconds after the answer, and only when something was actually wrong.
        streamed_answer = "".join(pieces)
        yield "stage", {"stage": "verifying"}
        with profile.stage("verification"):
            _final, trailing, vmeta = verification.verify(
                question, effective_route, streamed_answer,
                sql_result=sql_result, rag_chunks=rag_chunks, web_pages=web_pages,
            )
        if trailing:
            pieces.append(trailing)
            yield "token", trailing

        for note in notes:
            note_text = "\n\n" + note
            pieces.append(note_text)
            yield "token", note_text

        final_text = "".join(pieces)

        # Cache only a clean, verified-or-unflagged answer. `degraded` covers the
        # case where a source was down: that answer describes a temporary outage
        # and must not be replayed once the source is back.
        cache.store(
            question, final_text, effective_route, embed_text, degraded=bool(notes)
        )
        # Hand the answer to anyone who coalesced behind this request. Done here
        # rather than only in the wrapper's `finally` so waiters get the real
        # text, not None.
        if not notes:
            cache.finish(question, final_text, effective_route)

        logger.info(
            "streamed answer question=%r route=%s degraded=%s verification=%s",
            question, effective_route, bool(notes), vmeta.get("verification"),
        )
        profile.log(question)
        yield "done", {
            "answer": final_text,
            "verification": vmeta,
            # Per-stage timings ride along on the done event so latency can be
            # measured from a real client, not only read out of server logs.
            "profile": profile.as_dict(),
        }


def _sql_meta(sql_result):
    if sql_result is None:
        return None
    return {
        "generated_sql": sql_result.generated_sql,
        "error": sql_result.error,
        "row_count": len(sql_result.rows) if sql_result.rows else 0,
    }


def _rag_meta(rag_chunks):
    if not rag_chunks:
        return None
    return [
        {"table": c.table, "row_id": c.row_id, "score": round(c.score, 4)}
        for c in rag_chunks
    ]


def _web_meta(web_pages):
    if not web_pages:
        return None
    return [p.to_dict() for p in web_pages]
