# Copyright (c) 2026 Yash Garad. All rights reserved.

import time
from concurrent.futures import ThreadPoolExecutor

from rag_agent.service import retrieve
from router_agent.classifier import classify
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer
from verification_agent.service import verify_and_correct

from . import similarity

# The three configurations being compared.
#   full      -> the swarm as built: the router picks SQL / RAG / BOTH.
#   rag_only  -> ablation: force RAG, never call the SQL agent.
#   sql_only  -> ablation: force SQL, never call the RAG agent.
CONFIGS = ("full", "rag_only", "sql_only")

RAG_TOP_K = 5


def _resolve_route(config, question):
    if config == "rag_only":
        return "RAG", "forced RAG (ablation)"
    if config == "sql_only":
        return "SQL", "forced SQL (ablation)"
    # full: use the real router, mirroring the orchestrator's BOTH fallback.
    rr = classify(question)
    if rr.error:
        return "BOTH", f"router error ({rr.error}); defaulted to BOTH"
    return rr.route, rr.reason


def _gather_sources(route, question):
    """Runs SQL and/or RAG per the route, in parallel when both are needed —
    same concurrency the orchestrator uses, so latency is representative."""
    sql_result = None
    rag_chunks = None
    needs_sql = route in ("SQL", "BOTH")
    needs_rag = route in ("RAG", "BOTH")

    if needs_sql and needs_rag:
        with ThreadPoolExecutor(max_workers=2) as pool:
            sql_future = pool.submit(sql_ask, question, True)
            rag_future = pool.submit(retrieve, question, RAG_TOP_K)
            sql_result = sql_future.result()
            rag_chunks = rag_future.result()
    elif needs_sql:
        sql_result = sql_ask(question, execute=True)
    elif needs_rag:
        rag_chunks = retrieve(question, top_k=RAG_TOP_K)

    return sql_result, rag_chunks


def _agents_used(route):
    return {
        "SQL": "sql",
        "RAG": "rag",
        "BOTH": "sql+rag",
    }.get(route, route.lower())


def _verification_flag(claims, errored):
    if errored:
        return "error"
    if not claims:
        return "na"
    flagged = [c for c in claims if not c["supported"]]
    return "fail" if flagged else "pass"


def run_one(config, question, ground_truth, threshold=similarity.DEFAULT_THRESHOLD):
    """Runs a single (config, question) through router -> SQL/RAG -> synthesis
    -> verification, timing each stage and comparing to ground truth. Returns
    a flat dict of everything worth logging. Never raises: any failure is
    captured in the 'error' field and the row is marked incorrect."""
    row = {
        "question": question,
        "config_used": config,
        "ground_truth_answer": ground_truth,
        "route_used": None,
        "route_reason": None,
        "agents_used": None,
        "generated_sql": None,
        "sql_row_count": None,
        "sql_error": None,
        "rag_chunk_count": None,
        "rag_top_score": None,
        "rag_chunks": None,
        "synthesis_answer": None,
        "final_answer": None,
        "verification_flag": "na",
        "verification_claims_total": 0,
        "verification_flagged_count": 0,
        "verification_was_corrected": False,
        "semantic_similarity": None,
        "string_similarity": None,
        "correctness_basis": None,
        "correct": "no",
        "correct_post_verification": "no",
        "pipeline_ms": None,
        "verification_ms": None,
        "latency_ms": None,
        "error": None,
    }

    t_start = time.perf_counter()
    try:
        route, reason = _resolve_route(config, question)
        row["route_used"] = route
        row["route_reason"] = reason
        row["agents_used"] = _agents_used(route)

        sql_result, rag_chunks = _gather_sources(route, question)

        if sql_result is not None:
            row["generated_sql"] = sql_result.generated_sql
            row["sql_error"] = sql_result.error
            row["sql_row_count"] = len(sql_result.rows) if sql_result.rows else 0
        if rag_chunks is not None:
            row["rag_chunk_count"] = len(rag_chunks)
            row["rag_top_score"] = round(rag_chunks[0].score, 4) if rag_chunks else None
            row["rag_chunks"] = " | ".join(
                f"{c.table}#{c.row_id}({c.score:.3f}): {c.text}" for c in rag_chunks
            )

        synthesis_answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)
        row["synthesis_answer"] = synthesis_answer
        pipeline_ms = (time.perf_counter() - t_start) * 1000
        row["pipeline_ms"] = round(pipeline_ms, 1)

        # Verification pass (not in the live /api/ask/ pipeline, but part of
        # what this experiment measures per the spec).
        verif_errored = False
        t_verif = time.perf_counter()
        try:
            vresult = verify_and_correct(question, route, synthesis_answer, sql_result=sql_result, rag_chunks=rag_chunks)
            row["verification_claims_total"] = len(vresult.claims)
            row["verification_flagged_count"] = sum(1 for c in vresult.claims if not c["supported"])
            row["verification_was_corrected"] = vresult.was_corrected
            row["final_answer"] = vresult.final_answer
        except Exception as exc:  # verification is best-effort; don't lose the row
            verif_errored = True
            row["final_answer"] = synthesis_answer
            row["error"] = f"verification failed: {exc}"
        row["verification_ms"] = round((time.perf_counter() - t_verif) * 1000, 1)
        row["verification_flag"] = _verification_flag(
            [] if verif_errored else vresult.claims, verif_errored
        )

        row["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

        # Correctness is scored on the synthesis answer — that's the system's
        # actual output "as built" (verification isn't deployed in /api/ask/).
        # We also score the post-verification answer separately for comparison.
        score = similarity.score_answer(synthesis_answer, ground_truth, threshold=threshold)
        row["semantic_similarity"] = score["semantic_similarity"]
        row["string_similarity"] = score["string_similarity"]
        row["correctness_basis"] = score["correctness_basis"]
        row["correct"] = "yes" if score["correct"] else "no"

        post_score = similarity.score_answer(row["final_answer"] or synthesis_answer, ground_truth, threshold=threshold)
        row["correct_post_verification"] = "yes" if post_score["correct"] else "no"

    except Exception as exc:
        row["error"] = str(exc)
        row["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

    return row


# Column order for CSV export. The five columns the spec explicitly requires
# come first; everything else follows so nothing relevant is lost.
CSV_COLUMNS = [
    "question",
    "config_used",
    "correct",
    "latency_ms",
    "verification_flag",
    # --- everything else worth capturing for the paper ---
    "route_used",
    "agents_used",
    "semantic_similarity",
    "string_similarity",
    "correctness_basis",
    "correct_post_verification",
    "generated_sql",
    "sql_row_count",
    "sql_error",
    "rag_chunk_count",
    "rag_top_score",
    "verification_claims_total",
    "verification_flagged_count",
    "verification_was_corrected",
    "pipeline_ms",
    "verification_ms",
    "route_reason",
    "final_answer",
    "synthesis_answer",
    "ground_truth_answer",
    "rag_chunks",
    "error",
]
