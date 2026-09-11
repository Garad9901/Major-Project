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
    # The bound is sized lazily from measured p50. Under SimpleTestCase the
    # database is unavailable, so measurement returns None and the fallback is
    # used - which makes these tests deterministic rather than dependent on
    # whatever query_profile happens to contain.
    module.recompute_admission()
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


class AdmissionIsDerivedFromWhatItGovernsTests(SimpleTestCase):
    """The bound follows the queue timeout and the measured p50, not the threads.

    CHANGED SHIPPED TEST. This class previously asserted the bound was derived
    from GUNICORN_THREADS // 3. That derivation was wrong: thread count bounds
    how many requests can be HELD, not how many can be SERVED. With a serial
    queue, position k waits ~(k-1) x p50, so admitting 8 against a 25 s timeout
    and a ~40 s p50 meant 7 people held a thread for 25 s and were refused
    anyway - the very cost the bound exists to remove, only smaller and
    invisible.

    The property PRESERVED from the old test: the bound is always strictly
    smaller than the thread count. That margin is what keeps the fast path
    unblockable, and it is now a ceiling on the derivation rather than the
    derivation itself.
    """

    def tearDown(self):
        from orchestrator import concurrency
        importlib.reload(concurrency)

    def test_ceil_timeout_over_p50_plus_one(self):
        from orchestrator.concurrency import derive_max_admitted

        # 25 s timeout, ~40 s p50: only position 1 is servable, plus one.
        self.assertEqual(derive_max_admitted(25, 40.0, 24), 2)
        # 25 s timeout against the reference 87 s p50: same answer.
        self.assertEqual(derive_max_admitted(25, 87.0, 24), 2)
        # 120 s timeout, ~40 s p50: positions 1-3 reachable, plus one.
        self.assertEqual(derive_max_admitted(120, 40.0, 24), 4)

    def test_thread_count_remains_a_strict_ceiling(self):
        from orchestrator.concurrency import derive_max_admitted

        # A tiny p50 would derive an enormous bound; the ceiling holds it at
        # threads - 1 so at least one thread is always free for the fast path.
        for threads in (2, 4, 24):
            with self.subTest(threads=threads):
                self.assertEqual(derive_max_admitted(120, 0.5, threads), threads - 1)

    def test_never_below_one(self):
        from orchestrator.concurrency import derive_max_admitted

        self.assertEqual(derive_max_admitted(1, 1000.0, 24), 2)   # ceil(0.001)+1
        self.assertEqual(derive_max_admitted(1, 1000.0, 1), 1)    # ceiling at 1

    def test_fallback_is_reported_when_nothing_is_measured(self):
        # Under SimpleTestCase there is no database, so this is the fresh-
        # install case: the source must SAY it is a fallback, not pass a
        # constant off as a measurement.
        concurrency, patcher = _reload(threads=24, queue_timeout=25)
        self.addCleanup(patcher.stop)
        self.assertEqual(concurrency.ADMISSION_SOURCE, "fallback")
        self.assertEqual(concurrency.MAX_ADMITTED, 2)   # ceil(25/87)+1

    def test_an_explicit_override_wins_and_is_labelled(self):
        concurrency, patcher = _reload(max_admitted=3, threads=24)
        self.addCleanup(patcher.stop)
        self.assertEqual(concurrency.MAX_ADMITTED, 3)
        self.assertEqual(concurrency.ADMISSION_SOURCE, "override")

    def test_recompute_swaps_the_bound_without_stranding_holders(self):
        # A request that acquired the OLD semaphore must release the OLD one.
        # Otherwise recomputing while a request is in flight would leak a
        # ticket from the new bound, or double-release into the old.
        concurrency, patcher = _reload(max_admitted=2, queue_timeout=30)
        self.addCleanup(patcher.stop)
        old_sem = concurrency._admission

        held = threading.Event()
        release = threading.Event()

        def occupy():
            with concurrency.llm_slot(label="holder"):
                held.set()
                release.wait(timeout=10)

        t = threading.Thread(target=occupy, daemon=True)
        t.start()
        self.assertTrue(held.wait(timeout=5))
        self.assertEqual(old_sem._value, 1)

        # Recompute while the holder is inside. Override forces a known size.
        with mock.patch.dict(os.environ, {"LLM_MAX_ADMITTED": "5"}):
            concurrency.recompute_admission()
        new_sem = concurrency._admission
        self.assertIsNot(new_sem, old_sem)
        self.assertEqual(new_sem._value, 5)          # untouched by the holder

        release.set()
        t.join(timeout=5)
        self.assertEqual(old_sem._value, 2)          # released to the OLD one
        self.assertEqual(new_sem._value, 5)          # new one never touched


class QueuePositionTests(SimpleTestCase):
    def tearDown(self):
        from orchestrator import concurrency
        importlib.reload(concurrency)

    def test_position_is_one_when_nobody_is_waiting(self):
        concurrency, patcher = _reload(max_admitted=3, queue_timeout=30)
        self.addCleanup(patcher.stop)
        self.assertEqual(concurrency.queue_position(), 1)

    def test_position_counts_everyone_ahead(self):
        concurrency, patcher = _reload(max_admitted=3, queue_timeout=30)
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
        # One inside (still counted in _waiting until it exits) -> next is 2nd.
        self.assertEqual(concurrency.queue_position(), 2)
        release.set()
        t.join(timeout=5)
        self.assertEqual(concurrency.queue_position(), 1)


class FirstUseDoesNotDeadlockTests(SimpleTestCase):
    """The very first llm_slot() of a process must return.

    _get_admission() holds _admission_lock while calling recompute_admission(),
    which takes it again. With a plain Lock that deadlocked on the FIRST model
    request after every deploy. The other tests here never noticed because they
    call recompute_admission() directly; the full suite noticed by hanging for
    ten minutes. This test enters the slot on a fresh module, in a thread, with
    a deadline - so a regression fails in seconds instead of hanging a CI run.
    """

    def tearDown(self):
        from orchestrator import concurrency
        importlib.reload(concurrency)

    def test_lazy_initialisation_from_inside_llm_slot(self):
        with mock.patch.dict(os.environ, {"LLM_MAX_ADMITTED": "2", "LLM_QUEUE_TIMEOUT": "30"}):
            from orchestrator import concurrency
            concurrency = importlib.reload(concurrency)
            # Deliberately NOT calling recompute_admission(): the slot itself
            # must be able to size the bound on first use.
            self.assertIsNone(concurrency._admission)

            entered = threading.Event()

            def first_use():
                with concurrency.llm_slot(label="first"):
                    entered.set()

            t = threading.Thread(target=first_use, daemon=True)
            t.start()
            self.assertTrue(
                entered.wait(timeout=5),
                "first llm_slot() never returned - the admission lock is not reentrant",
            )
            t.join(timeout=5)
            self.assertEqual(concurrency.MAX_ADMITTED, 2)
