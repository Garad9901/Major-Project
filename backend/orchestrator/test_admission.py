# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Model requests must never be able to occupy every worker thread.

THE DEFECT THIS PROTECTS AGAINST

gunicorn runs `gthread`: a request holds one worker THREAD for its whole life,
and llm_slot's `_slots.acquire(timeout=...)` blocks while holding it. With the
shipped 4 threads, four model questions consumed all of them and a fast-path
question that needs no model could not be served at all. Measured before the
bound existed:

    fast path, idle system          177 / 189 / 367 ms
    fast path, 4 model requests     17,173 ms          <- 47-97x

8s of saturation + 17.2s of waiting = 25.2s, which is exactly when three model
requests hit the 25s queue timeout and released their threads. The fast path was
not waiting for GENERATION; it was waiting for the QUEUE TIMEOUT. So starvation
scaled with LLM_QUEUE_TIMEOUT, and docs/SCALING.md's recommendation to raise
that to 120 would have made it five times worse.

THE PROPERTY

At most MAX_ADMITTED requests may be inside llm_slot at once. The rest are
refused IMMEDIATELY — in microseconds, releasing the thread — rather than
blocking for the queue timeout. Threads beyond the bound therefore remain
available to the deterministic path no matter how deep the model queue gets.

These are unit tests of the bound itself. The end-to-end proof, against a real
saturated server, is in docs/SCALING.md.
"""

import importlib
import os
import threading
import time
from unittest import mock

from django.test import SimpleTestCase

from common.exceptions import AssistantBusy


def _reload(max_admitted=None, threads=None, queue_timeout=None):
    """Reimport concurrency with a given sizing. Restored by the caller."""
    env = {}
    if max_admitted is not None:
        env["LLM_MAX_ADMITTED"] = str(max_admitted)
    if threads is not None:
        env["GUNICORN_THREADS"] = str(threads)
    if queue_timeout is not None:
        env["LLM_QUEUE_TIMEOUT"] = str(queue_timeout)
    patcher = mock.patch.dict(os.environ, env)
    patcher.start()
    from orchestrator import concurrency
    module = importlib.reload(concurrency)
    return module, patcher


class AdmissionIsBoundedTests(SimpleTestCase):
    def tearDown(self):
        from orchestrator import concurrency
        importlib.reload(concurrency)

    def test_requests_beyond_the_bound_are_refused(self):
        concurrency, patcher = _reload(max_admitted=2, queue_timeout=30)
        self.addCleanup(patcher.stop)

        held = threading.Event()
        release = threading.Event()
        errors = []

        def occupy():
            try:
                with concurrency.llm_slot(label="test"):
                    held.set()
                    release.wait(timeout=10)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        # One request takes the single LLM slot and holds it.
        t = threading.Thread(target=occupy, daemon=True)
        t.start()
        self.assertTrue(held.wait(timeout=5), "first request never acquired a slot")

        # A second is admitted and waits for the slot (this is the queue).
        second_admitted = threading.Event()

        def queue_up():
            try:
                with concurrency.llm_slot(label="second"):
                    pass
            except AssistantBusy:
                pass
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        t2 = threading.Thread(target=queue_up, daemon=True)
        t2.start()
        # Give it a moment to take the second admission ticket.
        for _ in range(50):
            if concurrency._admission._value == 0:
                break
            time.sleep(0.02)

        # The THIRD must be refused immediately rather than blocking.
        started = time.perf_counter()
        with self.assertRaises(AssistantBusy):
            with concurrency.llm_slot(label="third"):
                pass
        elapsed = time.perf_counter() - started

        release.set()
        t.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(errors, [])

        # THE POINT: refused in well under the queue timeout. If this ever
        # approaches QUEUE_TIMEOUT_SECONDS the thread is being held again and
        # the starvation is back.
        self.assertLess(
            elapsed, 1.0,
            f"refusal took {elapsed:.2f}s — the thread was held, not released",
        )

    def test_a_refused_request_does_not_leak_its_ticket(self):
        concurrency, patcher = _reload(max_admitted=1, queue_timeout=30)
        self.addCleanup(patcher.stop)

        held = threading.Event()
        release = threading.Event()

        def occupy():
            with concurrency.llm_slot(label="holder"):
                held.set()
                release.wait(timeout=10)

        t = threading.Thread(target=occupy, daemon=True)
        t.start()
        self.assertTrue(held.wait(timeout=5))

        # Refuse several times; each must return its ticket, or the bound
        # would erode until nothing could ever be admitted again.
        for _ in range(5):
            with self.assertRaises(AssistantBusy):
                with concurrency.llm_slot(label="refused"):
                    pass

        release.set()
        t.join(timeout=5)

        # Fully released afterwards.
        with concurrency.llm_slot(label="after"):
            pass
        self.assertEqual(concurrency._admission._value, concurrency.MAX_ADMITTED)

    def test_a_queue_timeout_returns_its_ticket(self):
        # The slot is held but the queue timeout expires. The waiter must give
        # back its admission ticket, not just its place in the queue.
        concurrency, patcher = _reload(max_admitted=2, queue_timeout=0.2)
        self.addCleanup(patcher.stop)

        held = threading.Event()
        release = threading.Event()

        def occupy():
            with concurrency.llm_slot(label="holder"):
                held.set()
                release.wait(timeout=10)

        t = threading.Thread(target=occupy, daemon=True)
        t.start()
        self.assertTrue(held.wait(timeout=5))

        with self.assertRaises(AssistantBusy):
            with concurrency.llm_slot(label="times-out"):
                pass

        release.set()
        t.join(timeout=5)
        self.assertEqual(concurrency._admission._value, concurrency.MAX_ADMITTED)


class AdmissionIsDerivedFromThreadsTests(SimpleTestCase):
    def tearDown(self):
        from orchestrator import concurrency
        importlib.reload(concurrency)

    def test_bound_is_smaller_than_the_thread_pool(self):
        # If this ever equalled the thread count the bound would do nothing:
        # model requests could still take every thread. The margin IS the fix.
        for threads in (4, 12, 24, 48):
            concurrency, patcher = _reload(threads=threads)
            try:
                self.assertLess(
                    concurrency.MAX_ADMITTED, threads,
                    f"admission {concurrency.MAX_ADMITTED} leaves no thread free at {threads}",
                )
                self.assertGreaterEqual(concurrency.MAX_ADMITTED, 1)
            finally:
                patcher.stop()

    def test_an_explicit_override_wins(self):
        concurrency, patcher = _reload(max_admitted=3, threads=24)
        self.addCleanup(patcher.stop)
        self.assertEqual(concurrency.MAX_ADMITTED, 3)
