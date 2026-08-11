# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from common import llm_metrics
from common.exceptions import (
    DatabaseUnavailable,
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


# ---------------------------------------------------------------------------
# TWO STATES THAT LOOK ALIKE AND ARE NOT
# ---------------------------------------------------------------------------
# "the query ran and matched nothing"   -> a fact about the college
# "the query could not run at all"      -> a fact about our infrastructure
#
# Only the first is something to tell a student about their college. Conflating
# them produces the worst output this system can emit: a confident, specific
# negative caused by a bug or an outage. During resilience testing, with
# Postgres stopped, the model wrote
#
#     "The college records do not cover the total number of faculty holding
#      the Lecturer rank"
#
# against a table holding 3,053 of them.
#
# THREE PROMPT-LEVEL ATTEMPTS FAILED TO STOP THIS, so the decision has been
# taken away from the model. In the unavailable case the wording below is
# returned from code and the model is either not called at all, or is called
# only for the retrieval half and never gets to touch this text. There is no
# instruction it can misread and no template it can prefer, because there is no
# instruction — see _generate_stream.
UNAVAILABLE_MESSAGE = (
    "I couldn't retrieve that information right now due to a temporary system "
    "issue. Please try again shortly."
)


class _UnavailableSql:
    """Stands in for a SQL result when the database could not be reached.

    Duck-types sql_agent.service.SqlAgentResult well enough for the consumers
    that matter — synthesis_agent.untrusted.fence_sql_rows,
    verification_agent.service._format_sql_section and orchestrator._sql_meta —
    all of which branch on `.error` first.

    `unavailable` is what the orchestrator branches on. It is a separate flag
    rather than an isinstance check so the distinction survives anything that
    passes a different object with the same shape, and so the intent is legible
    at the call site: `if _sql_unavailable(x)` says what it means.

    NOTE that this object is still handed to VERIFICATION, which does need the
    distinction spelled out in prose — a verifier told "no rows" would confirm
    a false negative as consistent with its evidence. That is why the wording in
    untrusted.py stays even though synthesis no longer relies on it.
    """

    rows = None
    columns = None
    generated_sql = None
    unavailable = True

    def __init__(self, exc):
        self.error = f"the records database was unreachable ({exc})"


def _sql_unavailable(sql_result):
    """True when the lookup could not RUN, as opposed to running and finding
    nothing. `sql_result is None` (route needed no SQL) is not unavailability,
    and neither is an empty `.rows`."""
    return bool(getattr(sql_result, "unavailable", False))


# Sentences asserting that the college holds no such record. Matched ONLY on the
# degraded path, where such a statement is known to be false — the lookup did
# not run, so nothing was established about what the records contain.
_ABSENCE_CLAIM_RE = re.compile(
    r"\b("
    r"records?\s+(?:do|does)\s*n[o']t\s+cover"
    r"|records?\s+(?:do|does)\s+not\s+cover"
    r"|(?:do|does)\s*n[o']t\s+(?:cover|contain|include|have)\s+"
    r"|(?:do|does)\s+not\s+(?:cover|contain|include|have)\s+"
    r"|there\s+(?:are|is)\s+no\s+"
    r"|no\s+(?:records?|data|information)\s+(?:on|about|for|of)\b"
    r"|(?:is|are)\s+not\s+(?:available|present|recorded|listed)\b"
    r"|(?:isn|aren)'t\s+(?:available|in\s+the\s+records)\b"
    r")",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _strip_false_absence(text):
    """Remove sentences claiming the records hold nothing. Returns (text, dropped).

    USED ONLY WHEN THE LOOKUP WAS UNAVAILABLE. On that path such a sentence is
    false by construction: the query never ran, so nothing at all was learned
    about what the records contain. Everywhere else these phrasings are correct
    and wanted, which is why this is not a global filter.

    CONSERVATIVE ON PURPOSE. A sentence is dropped only if it matches AND
    carries no digit. Numbers on this path come from retrieved passages and are
    the substance of the answer; a sentence like "63 Lecturers do not have a
    recorded score" is a real finding from real data and must survive. Deleting
    model prose is a blunt instrument, so it is aimed narrowly.

    If every sentence is dropped, the caller is left with the unavailability
    note alone — which is the honest answer in that case anyway.
    """
    if not text:
        return "", []
    kept, dropped = [], []
    for sentence in _SENTENCE_SPLIT_RE.split(text.strip()):
        if not sentence.strip():
            continue
        if _ABSENCE_CLAIM_RE.search(sentence) and not re.search(r"\d", sentence):
            dropped.append(sentence.strip())
        else:
            kept.append(sentence.strip())
    return " ".join(kept), dropped


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
    source is down. Returns (sql_result, rag_chunks, effective_route, notes,
    web_pages).

    An effective route of "NONE" means nothing usable came back and the caller
    should answer with UNAVAILABLE_MESSAGE. VectorStoreUnavailable still
    propagates from the RAG-only path, where a clean "descriptive search is
    down" message is the better answer. LLMUnavailable from the embed/generate
    steps propagates untouched — if the LLM is down, the whole request cannot be
    served anyway.
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
                # Marked unavailable rather than left as None. None renders as
                # "Database rows: none." to the verifier, which would then
                # confirm a false negative as consistent with its evidence.
                sql_result = _UnavailableSql(exc)
            try:
                rag_chunks = f_rag.result()
            except VectorStoreUnavailable as exc:
                logger.warning("RAG source down (route=BOTH), degrading to SQL-only: %s", exc)
                notes.append(RAG_DOWN_NOTE)

        # THE EFFECTIVE ROUTE IS WHAT ACTUALLY ANSWERED, not what was planned.
        # It is written to the audit log, so labelling a question BOTH when the
        # database was unreachable and only retrieval contributed makes the
        # record wrong about how the answer was produced — which is precisely
        # what an investigator reads it for. An unavailable SQL result is
        # therefore not "SQL happened".
        sql_answered = sql_result is not None and not _sql_unavailable(sql_result)
        if sql_answered and rag_chunks is None:
            effective = "SQL"
        elif rag_chunks is not None and not sql_answered:
            effective = "RAG"
        elif not sql_answered and rag_chunks is None:
            # Both sources gone. Not an exception: the caller turns this into
            # the deterministic unavailability message, which is a better
            # answer than a generic "service unavailable" error page.
            effective = "NONE"
        else:
            effective = "BOTH"
        return sql_result, rag_chunks, effective, notes, []

    if needs_sql:
        # SQL-only. A database outage here used to raise ServiceUnavailable and
        # surface as a generic error. It now returns the unavailable marker so
        # the caller answers with UNAVAILABLE_MESSAGE — same information, but
        # phrased as something that happened rather than as a failure page, and
        # crucially never routed through the model.
        try:
            sql_result = _run_sql(question, profile)
        except DatabaseUnavailable as exc:
            logger.warning("SQL source down (route=SQL): %s", exc)
            notes.append(DB_DOWN_NOTE)
            return _UnavailableSql(exc), None, "NONE", notes, []
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

        # Same two branches as the streaming path, kept in step deliberately:
        # a caller using the blocking variant must not get a model-authored
        # description of an outage that the streaming variant refuses to
        # produce. See _generate_stream for the reasoning.
        if _sql_unavailable(sql_result) and not rag_chunks and not web_pages:
            logger.warning(
                "records lookup unavailable and no retrieval fallback for %r — "
                "returning the fixed message without calling the model", question[:60],
            )
            return {
                "question": question,
                "route": effective_route,
                "route_reason": reason,
                "answer": UNAVAILABLE_MESSAGE,
                "degraded": True,
                "notes": notes,
                "sql": _sql_meta(sql_result),
                "rag": None,
                "web": None,
                "verification": {"verification": "not_applicable"},
            }

        prefix = ""
        synthesis_sql = sql_result
        if _sql_unavailable(sql_result) and rag_chunks:
            prefix = UNAVAILABLE_MESSAGE + "\n\n"
            synthesis_sql = None
            notes = [n for n in notes if n != DB_DOWN_NOTE]

        generated = synthesize_answer(
            question, effective_route, sql_result=synthesis_sql, rag_chunks=rag_chunks,
            web_pages=web_pages,
        )
        if prefix:
            generated, dropped = _strip_false_absence(generated)
            if dropped:
                logger.warning(
                    "removed %d absence claim(s) from a degraded answer for %r: %r",
                    len(dropped), question[:60], dropped,
                )
        answer = prefix + generated
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

    degraded = bool(notes) or bool(prefix)
    logger.info("answered question=%r route=%s degraded=%s", question, effective_route, degraded)
    return {
        "question": question,
        "route": effective_route,
        "route_reason": reason,
        "answer": answer,
        "degraded": degraded,
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
    # Created out here rather than inside _generate_stream so the cache lookup
    # — which embeds the question, an Ollama round trip — is measured as a
    # stage instead of disappearing into unattributed overhead. It sits on the
    # critical path to the first token for every question, hit or miss.
    profile = Profile()

    if bypass_cache:
        logger.info("cache bypassed (regenerate) for %r", question[:60])
        yield from _generate_stream(question, profile)
        return

    # CACHE CHECK BEFORE THE SLOT, DELIBERATELY.
    #
    # Doing it inside llm_slot() would make every cached answer queue behind
    # whoever is currently generating — with LLM_MAX_CONCURRENCY=1 and fifty
    # simultaneous users, forty-nine of them would be told the assistant is busy
    # and then be handed an answer that was sitting in memory the whole time.
    # Out here, a hit costs no slot and blocks nobody.
    with profile.stage("cache_lookup"):
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
            with profile.stage("coalesce_wait"):
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
        profile.mark("synthesis_first_token")
        yield "token", answer
        # Cache hits are recorded too. Leaving them out would make the
        # percentiles describe only the slow path, and a p50 computed over
        # misses alone is not the p50 a user experiences.
        profile.log(question)
        _store_profile(question, cached_route, profile, {}, cached=how)
        yield "done", {
            "answer": answer,
            "verification": {"verification": "cached"},
            "profile": profile.as_dict(),
        }
        return

    try:
        yield from _generate_stream(question, profile)
    finally:
        # Always release waiters, including on error or client disconnect.
        # _generate_stream publishes the real result via cache.finish() on
        # success; this is the safety net that stops followers hanging.
        if leader:
            cache.finish(question)


def _generate_stream(question, profile=None):
    """The real pipeline. Separated so the coalescing wrapper above stays
    readable and so `finally` cleanup is unambiguous.

    `profile` is passed in by the caller so its clock starts at the beginning of
    the request rather than here — otherwise the cache lookup that precedes this
    would be invisible, and every reported total would be short by that much.
    """
    profile = profile or Profile()
    # Timed by bracketing the acquire rather than wrapping it in a stage(),
    # because llm_slot is itself a context manager whose body is the entire
    # pipeline — wrapping it would time the whole request and call it "waiting".
    wait_started = profile.total_ms
    with llm_slot(label=f"stream q={question[:40]!r}"):
        profile.add_stage("slot_wait", wait_started)
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

        # ------------------------------------------------------------------
        # THE LOOKUP COULD NOT RUN, AND THERE IS NOTHING ELSE TO ANSWER FROM.
        #
        # No LLM call at all. The model is not asked, so it cannot decide to
        # phrase this as "the college records do not cover X" — which is what
        # it did, repeatedly, when it was asked. This is the whole point: the
        # decision is removed rather than argued with.
        # ------------------------------------------------------------------
        if _sql_unavailable(sql_result) and not rag_chunks and not web_pages:
            logger.warning(
                "records lookup unavailable and no retrieval fallback for %r — "
                "returning the fixed message without calling the model", question[:60],
            )
            profile.mark("synthesis_first_token")
            yield "token", UNAVAILABLE_MESSAGE
            profile.log(question)
            _store_profile(question, effective_route, profile, {"verification": "skipped"})
            yield "done", {
                "answer": UNAVAILABLE_MESSAGE,
                # Nothing was generated, so there is nothing to fact-check. Said
                # explicitly rather than left absent, so this is not mistaken
                # for a check that ran and passed.
                "verification": {"verification": "not_applicable"},
                "profile": profile.as_dict(),
            }
            return

        # ------------------------------------------------------------------
        # THE LOOKUP COULD NOT RUN, BUT RETRIEVAL DID.
        #
        # The note is emitted as literal text BEFORE synthesis starts, and the
        # model is never shown it and never asked to produce it — so it cannot
        # reword it, contradict it, or drop it. The model's only job is the
        # retrieval half that follows, and it is handed no SQL section at all,
        # so it has nothing to describe as absent.
        # ------------------------------------------------------------------
        pieces = []
        degraded_prefix = _sql_unavailable(sql_result) and bool(rag_chunks)
        if degraded_prefix:
            prefix = UNAVAILABLE_MESSAGE + "\n\n"
            pieces.append(prefix)
            profile.mark("synthesis_first_token")
            yield "token", prefix
            # Withheld from synthesis on purpose: passing the unavailable
            # marker would put "Database lookup FAILED" in the prompt and
            # invite the model to write about it, which is the behaviour being
            # removed. Verification still receives the real object below.
            synthesis_sql = None
            # The trailing note said the same thing in different words. Saying
            # it twice — once leading, once trailing — reads as two separate
            # problems rather than one, so the trailing copy goes.
            notes = [n for n in notes if n != DB_DOWN_NOTE]
        else:
            synthesis_sql = sql_result

        first_token_seen = degraded_prefix
        synthesis_started = profile.total_ms
        # Drained here so the streamed call's own timings are the only thing
        # add_stage() picks up, not whatever the sources stage left behind.
        llm_metrics.start()
        stream = synthesize_answer_stream(
            question, effective_route, sql_result=synthesis_sql, rag_chunks=rag_chunks,
            web_pages=web_pages,
        )

        if degraded_prefix:
            # BUFFERED, NOT STREAMED, AND ONLY ON THIS PATH.
            #
            # Withholding the SQL section was not enough on its own. Measured:
            # handed no database data at all, the model still inferred absence
            # from the question and wrote
            #
            #   "The college records do not cover the total number of faculty
            #    holding the Lecturer rank across all departments."
            #
            # while the note directly above it said the lookup had failed. The
            # model cannot be talked out of this — three prompt attempts — so
            # the sentence is removed after the fact instead. That needs whole
            # sentences, and sentences span streamed chunks, so this branch
            # buffers.
            #
            # The cost is that these answers do not appear token by token. It
            # is paid only during an outage, and only after the note has
            # already been shown, so the user is not left watching nothing.
            generated = "".join(stream)
            cleaned, dropped = _strip_false_absence(generated)
            if dropped:
                logger.warning(
                    "removed %d absence claim(s) from a degraded answer for %r: %r",
                    len(dropped), question[:60], dropped,
                )
            if cleaned:
                pieces.append(cleaned)
                yield "token", cleaned
        else:
            for piece in stream:
                if not first_token_seen:
                    first_token_seen = True
                    profile.mark("synthesis_first_token")
                pieces.append(piece)
                yield "token", piece
        profile.add_stage("synthesis", synthesis_started)

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
        #
        # `degraded_prefix` is part of this test and not merely `notes`. When the
        # unavailability note is prepended, DB_DOWN_NOTE is removed from `notes`
        # to avoid saying the same thing twice — which would have left `notes`
        # empty and marked a degraded answer cacheable. An answer opening "I
        # couldn't retrieve that information right now" would then have been
        # replayed to everyone for the next half hour, including long after the
        # database came back.
        degraded = bool(notes) or degraded_prefix
        cache.store(
            question, final_text, effective_route, embed_text, degraded=degraded
        )
        # Hand the answer to anyone who coalesced behind this request. Done here
        # rather than only in the wrapper's `finally` so waiters get the real
        # text, not None.
        if not degraded:
            cache.finish(question, final_text, effective_route)

        logger.info(
            "streamed answer question=%r route=%s degraded=%s verification=%s",
            question, effective_route, degraded, vmeta.get("verification"),
        )
        profile.log(question)
        _store_profile(question, effective_route, profile, vmeta)
        yield "done", {
            "answer": final_text,
            "verification": vmeta,
            # Per-stage timings ride along on the done event so latency can be
            # measured from a real client, not only read out of server logs.
            "profile": profile.as_dict(),
        }


def _store_profile(question, route, profile, vmeta, cached=""):
    """Persist one question's stage timings. Best-effort, like the audit write.

    A profiler that can break an answer is worse than no profiler, so every
    failure here is swallowed after logging. Imported inside the function
    because this module is loaded before the app registry is ready.
    """
    try:
        from .models import QueryProfile

        totals = {"prompt_tokens": 0, "prompt_ms": 0.0, "gen_tokens": 0, "gen_ms": 0.0}
        for stage in profile.stages:
            llm = stage.get("llm") or {}
            for key in totals:
                value = llm.get(key)
                if value is not None:
                    totals[key] += value

        first_token = next(
            (s["start_ms"] for s in profile.stages if s["name"] == "synthesis_first_token"),
            None,
        )
        QueryProfile.objects.create(
            question=question,
            route=route or "",
            total_ms=profile.total_ms,
            ttft_ms=first_token,
            router_ms=profile.get("router"),
            sql_ms=profile.get("sql"),
            rag_ms=profile.get("rag"),
            web_ms=profile.get("web_fetch"),
            synthesis_ms=profile.get("synthesis"),
            verification_ms=profile.get("verification"),
            overhead_ms=profile.overhead_ms(),
            prompt_tokens=totals["prompt_tokens"] or None,
            prompt_ms=round(totals["prompt_ms"], 1) or None,
            gen_tokens=totals["gen_tokens"] or None,
            gen_ms=round(totals["gen_ms"], 1) or None,
            verification_tier=(vmeta or {}).get("tier") or "",
            cached=cached,
            stages=profile.as_dict(),
        )
    except Exception:
        logger.exception("could not store query profile for %r", question[:60])


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
