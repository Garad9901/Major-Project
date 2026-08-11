# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The decision about an unavailable lookup is taken away from the LLM.

THE HISTORY THESE TESTS LOCK DOWN
With Postgres stopped, the synthesis model wrote:

    "The college records do not cover the total number of faculty holding the
     Lecturer rank"

against a table holding 3,053 of them. A confident, specific negative, caused
by an outage — the failure shape the original production audit called the worst
this system has.

Three prompt-level attempts failed to stop it: the wording in
synthesis_agent/untrusted.py, routing the outage through that wording via
_UnavailableSql, and an explicit "never write this, write that instead"
template in the synthesis system prompt. The model kept its own template.

A fourth attempt was not made. The model is now either not called at all, or
called only for the retrieval half and never shown the note.

WHY THESE ASSERTIONS ARE PROGRAMMATIC
The failure only becomes visible when a person reads an answer during an
outage, which is the least likely moment for anyone to be reading carefully. A
test that has to be eyeballed is not a test of this.

Kept in a separate module from tests.py because it is about one specific
regression and reads better as a unit than as another class appended to a file
that is mostly about conversations.
"""

from unittest import mock

from common.exceptions import DatabaseUnavailable
from django.test import TestCase

from orchestrator import service


class _Chunk:
    """Minimal stand-in for rag_agent.service.RetrievedChunk."""

    table = "faculty_development_profiles"
    row_id = 1
    score = 0.9
    text = "Lecturers show an overall development index of 67.2 out of 100."


class _EmptyResult:
    """A query that RAN and matched nothing. Not the same thing at all."""

    rows = []
    columns = ["count"]
    error = None
    generated_sql = "SELECT count(*) FROM faculty_development WHERE 1=0;"


def _unavailable():
    return service._UnavailableSql(Exception("could not connect to database"))


class TwoStatesAreDistinguishedTests(TestCase):
    """"ran and found nothing" vs "could not run" — the whole basis of the fix."""

    def test_zero_rows_is_not_unavailability(self):
        self.assertFalse(service._sql_unavailable(_EmptyResult()))

    def test_no_sql_needed_is_not_unavailability(self):
        self.assertFalse(service._sql_unavailable(None))

    def test_a_failed_lookup_is_unavailability(self):
        self.assertTrue(service._sql_unavailable(_unavailable()))


class NoFallbackMeansNoModelCallTests(TestCase):
    """Case 1: the lookup could not run and there is nothing else to answer from."""

    def test_returns_the_fixed_message_and_never_calls_the_model(self):
        called = []

        def _must_not_run(*args, **kwargs):
            called.append(True)
            yield "this must never be generated"

        with mock.patch.object(
            service, "_gather_sources",
            return_value=(_unavailable(), None, "NONE", [service.DB_DOWN_NOTE], []),
        ), mock.patch.object(
            service, "synthesize_answer_stream", _must_not_run
        ), mock.patch.object(
            service, "_resolve_route", return_value=("SQL", "test")
        ):
            events = list(service._generate_stream("How many Lecturers are there?"))

        answer = "".join(payload for kind, payload in events if kind == "token")
        self.assertEqual(answer, service.UNAVAILABLE_MESSAGE)
        self.assertEqual(called, [], "the synthesis model was called and must not have been")

    def test_the_done_event_does_not_claim_a_check_was_performed(self):
        """Nothing was generated, so "verified" would be a lie of omission."""
        with mock.patch.object(
            service, "_gather_sources",
            return_value=(_unavailable(), None, "NONE", [], []),
        ), mock.patch.object(
            service, "_resolve_route", return_value=("SQL", "test")
        ):
            events = list(service._generate_stream("How many Lecturers are there?"))

        done = next(p for kind, p in events if kind == "done")
        self.assertEqual(done["verification"], {"verification": "not_applicable"})


class DegradedAnswerLeadsWithTheNoteTests(TestCase):
    """Case 2: retrieval worked, so the model writes the descriptive half only."""

    def _run(self, model_output, notes=None):
        with mock.patch.object(
            service, "_gather_sources",
            return_value=(
                _unavailable(), [_Chunk()], "RAG",
                list(notes if notes is not None else [service.DB_DOWN_NOTE]), [],
            ),
        ), mock.patch.object(
            service, "synthesize_answer_stream", lambda *a, **kw: iter([model_output])
        ), mock.patch.object(
            service, "_resolve_route", return_value=("BOTH", "test")
        ), mock.patch.object(
            service.verification, "verify",
            return_value=("ignored", "", {"verification": "off"}),
        ):
            events = list(service._generate_stream("How many Lecturers, and describe them?"))
        return "".join(payload for kind, payload in events if kind == "token")

    def test_answer_STARTS_WITH_the_hardcoded_note(self):
        """THE ASSERTION THIS CHANGE EXISTS FOR.

        startswith, not "contains". A note buried under three paragraphs that
        open "the college records do not cover X" is the bug, not the fix.

        The simulated model output is deliberately the exact sentence the real
        model kept producing, so this fails if the note stops leading even when
        the model misbehaves in precisely the observed way.
        """
        answer = self._run("The college records do not cover the total number of Lecturers.")

        self.assertTrue(
            answer.startswith(service.UNAVAILABLE_MESSAGE),
            f"answer did not start with the unavailability note. Got: {answer[:200]!r}",
        )

    def test_the_note_is_verbatim_and_not_reworded(self):
        answer = self._run("Some description of the passages.")
        self.assertEqual(answer[: len(service.UNAVAILABLE_MESSAGE)],
                         service.UNAVAILABLE_MESSAGE)

    def test_the_model_is_never_shown_the_unavailable_sql_result(self):
        """It cannot describe as absent something it was never handed."""
        seen = {}

        def _capture(question, route, sql_result=None, rag_chunks=None, web_pages=None):
            seen["sql_result"] = sql_result
            yield "prose about the passages"

        with mock.patch.object(
            service, "_gather_sources",
            return_value=(_unavailable(), [_Chunk()], "RAG", [service.DB_DOWN_NOTE], []),
        ), mock.patch.object(
            service, "synthesize_answer_stream", _capture
        ), mock.patch.object(
            service, "_resolve_route", return_value=("BOTH", "test")
        ), mock.patch.object(
            service.verification, "verify",
            return_value=("ignored", "", {"verification": "off"}),
        ):
            list(service._generate_stream("How many Lecturers, and describe them?"))

        self.assertIsNone(
            seen["sql_result"],
            "an unavailable SQL result reached synthesis; the model can then write "
            "about the outage, which is the behaviour being removed",
        )

    def test_the_note_is_not_also_repeated_at_the_end(self):
        """Leading note plus trailing DB_DOWN_NOTE reads as two faults, not one."""
        answer = self._run("Some description of the passages.")
        self.assertNotIn(service.DB_DOWN_NOTE, answer)

    def test_a_degraded_answer_is_never_offered_to_the_cache_as_clean(self):
        """Otherwise "I couldn't retrieve that" is replayed for half an hour.

        Guards the removal of DB_DOWN_NOTE from `notes` specifically: that left
        the list empty, and the cache decision used to key off exactly that
        list, so suppressing the duplicate note would have made the answer
        look cacheable.
        """
        with mock.patch.object(
            service, "_gather_sources",
            return_value=(_unavailable(), [_Chunk()], "RAG", [service.DB_DOWN_NOTE], []),
        ), mock.patch.object(
            service, "synthesize_answer_stream", lambda *a, **kw: iter(["prose"])
        ), mock.patch.object(
            service, "_resolve_route", return_value=("BOTH", "test")
        ), mock.patch.object(
            service.verification, "verify",
            return_value=("ignored", "", {"verification": "off"}),
        ), mock.patch.object(service.cache, "store") as store:
            list(service._generate_stream("q"))

        self.assertTrue(store.called)
        self.assertTrue(
            store.call_args.kwargs.get("degraded"),
            "a degraded answer was offered to the cache as clean",
        )


class EffectiveRouteReflectsWhatActuallyAnsweredTests(TestCase):
    """The route lands in the audit log, which is read to establish how an
    answer was produced. Labelling an outage BOTH makes that record wrong."""

    def test_says_RAG_when_only_retrieval_answered(self):
        with mock.patch.object(
            service, "_run_sql", side_effect=DatabaseUnavailable("down")
        ), mock.patch.object(service, "_run_rag", return_value=[_Chunk()]):
            _sql, _rag, effective, notes, _web = service._gather_sources("q", "BOTH")

        self.assertEqual(effective, "RAG")
        self.assertIn(service.DB_DOWN_NOTE, notes)

    def test_says_NONE_when_neither_source_answered(self):
        from common.exceptions import VectorStoreUnavailable

        with mock.patch.object(
            service, "_run_sql", side_effect=DatabaseUnavailable("down")
        ), mock.patch.object(
            service, "_run_rag", side_effect=VectorStoreUnavailable("down")
        ):
            sql_result, rag, effective, _notes, _web = service._gather_sources("q", "BOTH")

        self.assertEqual(effective, "NONE")
        self.assertTrue(service._sql_unavailable(sql_result))
        self.assertIsNone(rag)

    def test_sql_only_route_degrades_instead_of_raising(self):
        """It used to raise ServiceUnavailable and surface as a generic error;
        the fixed message is the same information, better phrased."""
        with mock.patch.object(
            service, "_run_sql", side_effect=DatabaseUnavailable("down")
        ):
            sql_result, _rag, effective, notes, _web = service._gather_sources("q", "SQL")

        self.assertEqual(effective, "NONE")
        self.assertTrue(service._sql_unavailable(sql_result))
        self.assertIn(service.DB_DOWN_NOTE, notes)


class AbsenceClaimsAreStrippedOnTheDegradedPathTests(TestCase):
    """Withholding the SQL section was not sufficient on its own.

    Handed no database data at all, the model STILL inferred absence from the
    question and wrote, directly beneath a note saying the lookup had failed:

        "The college records do not cover the total number of faculty holding
         the Lecturer rank across all departments."

    Measured live, with Postgres stopped. So the sentence is removed after the
    fact. This is deterministic code, not another instruction to the model.
    """

    def test_removes_the_exact_sentence_seen_in_production(self):
        kept, dropped = service._strip_false_absence(
            "The college records do not cover the total number of faculty holding "
            "the Lecturer rank across all departments. However, a summary shows an "
            "index averaging 67.2 out of 100."
        )
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("do not cover", kept)
        self.assertIn("67.2", kept)

    def test_handles_the_contracted_form(self):
        kept, _ = service._strip_false_absence(
            "The college records don't cover the total number of Lecturers. "
            "Teaching quality ranges between 60 and 67."
        )
        self.assertNotIn("cover", kept)
        self.assertIn("Teaching quality", kept)

    def test_keeps_a_sentence_that_carries_data(self):
        """A real finding from real passages must survive.

        "63 Lecturers do not have a recorded score" matches the absence
        pattern and is TRUE — it came from retrieved data. The digit guard is
        what protects it, and this test is why that guard exists.
        """
        text = "63 Lecturers do not have a recorded score. The average is 67.2."
        kept, dropped = service._strip_false_absence(text)
        self.assertEqual(dropped, [])
        self.assertEqual(kept, text)

    def test_leaves_an_ordinary_answer_completely_alone(self):
        text = "Lecturers show an overall development index of 67.2 out of 100."
        kept, dropped = service._strip_false_absence(text)
        self.assertEqual(kept, text)
        self.assertEqual(dropped, [])

    def test_dropping_everything_leaves_the_note_standing_alone(self):
        kept, dropped = service._strip_false_absence(
            "There are no records of that. The records do not cover it."
        )
        self.assertEqual(kept, "")
        self.assertEqual(len(dropped), 2)

    def test_end_to_end_the_degraded_answer_carries_no_absence_claim(self):
        """The whole point, through the real streaming path."""
        with mock.patch.object(
            service, "_gather_sources",
            return_value=(_unavailable(), [_Chunk()], "RAG", [service.DB_DOWN_NOTE], []),
        ), mock.patch.object(
            service, "synthesize_answer_stream",
            lambda *a, **kw: iter([
                "The college records do not cover the total number of Lecturers. ",
                "Their development index averages 67.2 out of 100.",
            ]),
        ), mock.patch.object(
            service, "_resolve_route", return_value=("BOTH", "test")
        ), mock.patch.object(
            service.verification, "verify",
            return_value=("ignored", "", {"verification": "off"}),
        ):
            events = list(service._generate_stream("How many Lecturers, and describe them?"))

        answer = "".join(payload for kind, payload in events if kind == "token")
        self.assertTrue(answer.startswith(service.UNAVAILABLE_MESSAGE))
        self.assertNotIn("do not cover", answer.lower())
        self.assertIn("67.2", answer, "the useful retrieval content was lost")
