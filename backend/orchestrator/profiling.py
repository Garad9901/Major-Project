# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Per-stage timing for one question, so latency claims can be checked.

WHY THIS EXISTS
"The system feels slow" is not actionable, and neither is a single end-to-end
number. A question costs four or five separate LLM round trips, and until each
one is timed separately every optimisation is a guess. This records where the
time actually goes.

It also answers a question that is otherwise argued about rather than measured:
whether the SQL and RAG branches genuinely overlap. Each stage records the
thread it ran on and its start/end offsets, so two stages running concurrently
are visible as overlapping intervals on different threads — proof rather than
assertion. See `overlap_report()`.

COST
`time.perf_counter()` twice per stage and a dict append. Against LLM calls
measured in seconds, that is unmeasurable. It is always on: a profiler you have
to enable is one you will not have enabled on the day you need it.
"""

import logging
import threading
import time
from contextlib import contextmanager

from common import llm_metrics

logger = logging.getLogger("orchestrator")


class Profile:
    """Timings for a single question. Not thread-safe by accident — the append
    is guarded, because SQL and RAG stages are recorded from worker threads."""

    def __init__(self):
        self._t0 = time.perf_counter()
        self._lock = threading.Lock()
        self.stages = []

    @contextmanager
    def stage(self, name):
        """Time one named stage. Records even when the body raises, because a
        stage that failed slowly is exactly what you want to see.

        Also attaches Ollama's own prompt-read/generation split for any LLM
        calls the body made. `llm_metrics.start()` at the top discards anything
        buffered from earlier on this thread, so a stage only ever claims the
        calls it actually made — this matters on pool workers, which are reused
        across requests.
        """
        llm_metrics.start()
        start = time.perf_counter()
        thread = threading.current_thread().name
        error = None
        try:
            yield
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            end = time.perf_counter()
            record = {
                "name": name,
                "start_ms": round((start - self._t0) * 1000, 1),
                "end_ms": round((end - self._t0) * 1000, 1),
                "ms": round((end - start) * 1000, 1),
                "thread": thread,
                "error": error,
            }
            llm = llm_metrics.summarise(llm_metrics.take())
            if llm:
                record["llm"] = llm
            with self._lock:
                self.stages.append(record)

    def add_stage(self, name, start_ms, end_ms=None):
        """Record a stage whose span is known but which could not be wrapped in
        `stage()`.

        Streaming synthesis needs this: the work is a generator consumed by the
        caller, so there is no block to wrap — entering a context manager around
        the `for` loop would also enclose the caller's per-token work and the
        SSE writes, and attribute them to synthesis.

        LLM metrics are drained the same way `stage()` drains them, which is
        what makes the streamed call's prompt/generation split appear in the
        profile at all.
        """
        end_ms = self.total_ms if end_ms is None else end_ms
        record = {
            "name": name,
            "start_ms": round(start_ms, 1),
            "end_ms": round(end_ms, 1),
            "ms": round(end_ms - start_ms, 1),
            "thread": threading.current_thread().name,
            "error": None,
        }
        llm = llm_metrics.summarise(llm_metrics.take())
        if llm:
            record["llm"] = llm
        with self._lock:
            self.stages.append(record)

    def mark(self, name):
        """Record a zero-width instant, e.g. 'first token emitted'."""
        now = time.perf_counter()
        with self._lock:
            self.stages.append({
                "name": name,
                "start_ms": round((now - self._t0) * 1000, 1),
                "end_ms": round((now - self._t0) * 1000, 1),
                "ms": 0.0,
                "thread": threading.current_thread().name,
                "error": None,
            })

    @property
    def total_ms(self):
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def get(self, name):
        """Duration of a named stage in ms, or None if it never ran."""
        for stage in self.stages:
            if stage["name"] == name:
                return stage["ms"]
        return None

    def overlap_report(self):
        """Did the SQL and RAG stages actually run at the same time?

        Returns None when the question did not use both. Otherwise a dict with
        the overlap in milliseconds and the sequential cost that overlap saved.
        Zero overlap on a BOTH question means the ThreadPoolExecutor is not
        doing what it is there for.
        """
        sql = next((s for s in self.stages if s["name"] == "sql"), None)
        rag = next((s for s in self.stages if s["name"] == "rag"), None)
        if not sql or not rag:
            return None
        overlap = min(sql["end_ms"], rag["end_ms"]) - max(sql["start_ms"], rag["start_ms"])
        wall = max(sql["end_ms"], rag["end_ms"]) - min(sql["start_ms"], rag["start_ms"])
        return {
            "sql_ms": sql["ms"],
            "rag_ms": rag["ms"],
            "sequential_would_be_ms": round(sql["ms"] + rag["ms"], 1),
            "actual_wall_ms": round(wall, 1),
            "overlap_ms": round(max(0.0, overlap), 1),
            "saved_ms": round(sql["ms"] + rag["ms"] - wall, 1),
            "different_threads": sql["thread"] != rag["thread"],
            "parallel": overlap > 0 and sql["thread"] != rag["thread"],
        }

    def covered_ms(self):
        """Wall time covered by at least one stage.

        A plain sum over stages double-counts the SQL and RAG branches, which
        run at the same time — on a BOTH question that sum can exceed the total
        and produce a negative overhead. This merges overlapping intervals
        first, so what it returns is real elapsed time.
        """
        spans = sorted(
            (s["start_ms"], s["end_ms"]) for s in self.stages if s["end_ms"] > s["start_ms"]
        )
        total = 0.0
        cur_start = cur_end = None
        for start, end in spans:
            if cur_end is None or start > cur_end:
                if cur_end is not None:
                    total += cur_end - cur_start
                cur_start, cur_end = start, end
            else:
                cur_end = max(cur_end, end)
        if cur_end is not None:
            total += cur_end - cur_start
        return round(total, 1)

    def overhead_ms(self):
        """Everything the named stages do NOT account for.

        This is the residual: waiting for an LLM slot, the cache lookup and its
        embedding call, JSON serialisation, the SSE writes between tokens, the
        audit and chat-history inserts. It is reported as one number rather than
        broken down further because the point of it is to be an upper bound on
        how much could ever be won back by making the plumbing faster — if it is
        small, the plumbing is not the problem and no further breakdown is
        needed.
        """
        return round(max(0.0, self.total_ms - self.covered_ms()), 1)

    def as_dict(self):
        return {
            "total_ms": self.total_ms,
            "covered_ms": self.covered_ms(),
            "overhead_ms": self.overhead_ms(),
            "stages": list(self.stages),
            "overlap": self.overlap_report(),
        }

    def log(self, question):
        """One line per question, ordered by start time, plus the overlap
        verdict when both data stages ran."""
        ordered = sorted(self.stages, key=lambda s: s["start_ms"])
        parts = " ".join(
            f"{s['name']}={s['ms']:.0f}ms@{s['start_ms']:.0f}"
            + (f"!{s['error']}" if s["error"] else "")
            for s in ordered
        )
        logger.info(
            "PROFILE q=%r total=%.0fms overhead=%.0fms %s",
            question[:60], self.total_ms, self.overhead_ms(), parts,
        )
        # The prompt-read / generation split, per stage that made an LLM call.
        # This is the line that says WHY a stage was slow, as opposed to which
        # stage was slow — see common/llm_metrics.py.
        for stage in ordered:
            llm = stage.get("llm")
            if not llm:
                continue
            logger.info(
                "PROFILE   %s: %d call(s) read %s tok in %sms, wrote %s tok in %sms, load %sms",
                stage["name"], llm["llm_calls"],
                llm.get("prompt_tokens"), llm.get("prompt_ms"),
                llm.get("gen_tokens"), llm.get("gen_ms"), llm.get("load_ms"),
            )
        overlap = self.overlap_report()
        if overlap:
            logger.info(
                "PROFILE parallel=%s sql=%.0fms rag=%.0fms overlap=%.0fms saved=%.0fms "
                "(sequential would be %.0fms, actual %.0fms)",
                overlap["parallel"], overlap["sql_ms"], overlap["rag_ms"],
                overlap["overlap_ms"], overlap["saved_ms"],
                overlap["sequential_would_be_ms"], overlap["actual_wall_ms"],
            )
