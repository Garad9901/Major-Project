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
        stage that failed slowly is exactly what you want to see."""
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
            with self._lock:
                self.stages.append({
                    "name": name,
                    "start_ms": round((start - self._t0) * 1000, 1),
                    "end_ms": round((end - self._t0) * 1000, 1),
                    "ms": round((end - start) * 1000, 1),
                    "thread": thread,
                    "error": error,
                })

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

    def as_dict(self):
        return {
            "total_ms": self.total_ms,
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
        logger.info("PROFILE q=%r total=%.0fms %s", question[:60], self.total_ms, parts)
        overlap = self.overlap_report()
        if overlap:
            logger.info(
                "PROFILE parallel=%s sql=%.0fms rag=%.0fms overlap=%.0fms saved=%.0fms "
                "(sequential would be %.0fms, actual %.0fms)",
                overlap["parallel"], overlap["sql_ms"], overlap["rag_ms"],
                overlap["overlap_ms"], overlap["saved_ms"],
                overlap["sequential_would_be_ms"], overlap["actual_wall_ms"],
            )
