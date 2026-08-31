# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Cross-process invalidation of the answer cache.

THE PROPERTY UNDER TEST
When the records change, no serving process may keep answering from entries
computed before the change.

WHY THIS IS NOT OBVIOUS, AND WHY IT IS TESTED RATHER THAN REVIEWED
The cache is module-level state inside the serving process. `manage.py` runs in
a DIFFERENT process, so the obvious implementation — a command that calls
cache.invalidate() — clears its own empty cache and reports success while the
worker carries on serving stale answers. Measured on the running stack before
this was fixed:

    ask #1 (cold)                                60 s
    a separate process reports                    0 entries
    ask #2                                        1 s   <- the worker HAS it
    invalidate() from a separate process   "cleared 0 entries"
    ask #3                                        0 s   <- still stale

These tests therefore never assert that "invalidate was called". They assert
that a process which did NOT do the clearing stops serving its own entries.
"""

from unittest import mock

from django.core.cache import cache as shared_cache
from django.core.management import call_command
from django.test import TestCase

from orchestrator import cache


def _vector(seed):
    """A deterministic unit-ish vector; the values do not matter, only that
    identical questions produce identical ones."""
    return [float(seed), 1.0, 0.0]


class GenerationTokenClearsOtherProcessesTests(TestCase):
    def setUp(self):
        cache.invalidate("test setup")
        cache._generation = None
        shared_cache.delete(cache._GENERATION_KEY)

    def tearDown(self):
        cache.invalidate("test teardown")
        cache._generation = None
        shared_cache.delete(cache._GENERATION_KEY)

    def _store(self, question="How many faculty are in Engineering?"):
        cache.store(question, "There are 42.", "SQL", lambda q: _vector(1))
        return question

    def test_a_stored_answer_is_served_back(self):
        """The baseline. Without this the other tests could pass vacuously."""
        q = self._store()
        hit = cache.lookup(q, lambda x: _vector(1))
        self.assertIsNotNone(hit, "the cache did not serve an answer it just stored")
        self.assertEqual(hit[0], "There are 42.")

    def test_a_bump_from_ANOTHER_process_drops_this_cache(self):
        """The actual defect.

        The bump is simulated the way a real one arrives: the shared token is
        changed WITHOUT touching this process's entries, exactly as a separate
        `manage.py` process would leave things. This process must notice on its
        next lookup.
        """
        q = self._store()
        self.assertIsNotNone(cache.lookup(q, lambda x: _vector(1)))

        # What a different process does, and NOTHING else. No call into this
        # process's invalidate() — that is the whole point.
        shared_cache.set(cache._GENERATION_KEY, "a-different-token", timeout=None)

        self.assertIsNone(
            cache.lookup(q, lambda x: _vector(1)),
            "a cached answer survived an invalidation raised by another process",
        )
        self.assertEqual(len(cache._entries), 0)

    def test_bump_generation_is_what_a_command_actually_calls(self):
        q = self._store()
        self.assertIsNotNone(cache.lookup(q, lambda x: _vector(1)))

        # Simulate the other process by bumping, then forgetting that this
        # process was the one that did it.
        token = cache.bump_generation("import:departments")
        self.assertIsNotNone(token)
        cache._generation = "whatever-this-process-last-saw"

        self.assertIsNone(cache.lookup(q, lambda x: _vector(1)))

    def test_an_unrelated_bump_does_not_clear_twice(self):
        """Once cleared and re-synced, a stable token must not keep clearing.

        A check that cleared on every lookup would disable the cache entirely
        while looking like it worked.
        """
        q = self._store()
        shared_cache.set(cache._GENERATION_KEY, "token-one", timeout=None)
        cache.lookup(q, lambda x: _vector(1))          # clears, syncs to token-one

        # The call re-stores; its return value is not needed here (the
        # question `q` is already held above).
        self._store(q)
        hit = cache.lookup(q, lambda x: _vector(1))
        self.assertIsNotNone(hit, "the cache cleared itself on an unchanged token")


class RedisUnreachableFailsClosedTests(TestCase):
    """If freshness cannot be established, do not serve.

    A stale fee or deadline delivered confidently is this system's worst
    outcome, so an unreachable Redis must not degrade to "serve whatever is in
    memory". It costs nothing real: sessions live in Redis too, so if it is down
    nobody is signed in to be served a stale answer.
    """

    def setUp(self):
        cache.invalidate("test setup")
        cache._generation = None

    def tearDown(self):
        cache.invalidate("test teardown")
        cache._generation = None
        shared_cache.delete(cache._GENERATION_KEY)

    def test_lookup_returns_nothing_when_the_token_cannot_be_read(self):
        cache.store("q", "cached answer", "SQL", lambda q: _vector(1))

        broken = mock.Mock()
        broken.get.side_effect = ConnectionError("redis is down")
        with mock.patch.object(cache, "_shared", return_value=broken):
            self.assertIsNone(
                cache.lookup("q", lambda x: _vector(1)),
                "served a cached answer without being able to prove it was current",
            )

    def test_store_declines_when_the_token_cannot_be_read(self):
        broken = mock.Mock()
        broken.get.side_effect = ConnectionError("redis is down")
        with mock.patch.object(cache, "_shared", return_value=broken):
            cache.store("q", "an answer", "SQL", lambda x: _vector(1))
        self.assertEqual(len(cache._entries), 0)

    def test_bump_reports_failure_rather_than_claiming_success(self):
        """The command branches on this. Returning a token here would make it
        print "cleared" after clearing nothing."""
        broken = mock.Mock()
        broken.set.side_effect = ConnectionError("redis is down")
        with mock.patch.object(cache, "_shared", return_value=broken):
            self.assertIsNone(cache.bump_generation("test"))


class ClearAnswerCacheCommandTests(TestCase):
    def tearDown(self):
        cache._generation = None
        shared_cache.delete(cache._GENERATION_KEY)

    def test_it_changes_the_shared_token(self):
        shared_cache.set(cache._GENERATION_KEY, "before", timeout=None)
        call_command("clear_answer_cache")
        self.assertNotEqual(shared_cache.get(cache._GENERATION_KEY), "before")

    def test_it_exits_non_zero_when_nothing_could_be_cleared(self):
        """An operator scripting a data load must be able to detect this.

        Reporting success here is the exact failure the command was written to
        avoid, so it is worth a test of its own.
        """
        broken = mock.Mock()
        broken.set.side_effect = ConnectionError("redis is down")
        with mock.patch.object(cache, "_shared", return_value=broken):
            with self.assertRaises(SystemExit) as raised:
                call_command("clear_answer_cache")
        self.assertEqual(raised.exception.code, 1)
