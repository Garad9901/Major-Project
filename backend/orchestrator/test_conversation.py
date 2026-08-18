# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Follow-up questions: resolution, the history window, and cache isolation.

THE BUG THESE LOCK DOWN
Every question was handled in isolation, so "how many departments are there?"
followed by "name them" sent the bare string "name them" to the router, the SQL
agent and synthesis. None of them could know what "them" was.

The cache tests are the ones most worth reading. A follow-up is the WORST case
for a semantic cache: "name them" and "list those" carry almost no text, so
they embed close together regardless of what conversation they came from. Keyed
on what the user typed, two unrelated conversations collide and the second user
is served the first one's answer with complete confidence.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache as django_cache
from django.test import TestCase

from orchestrator import conversation, service
from orchestrator.models import Conversation, Message


def _turns(*pairs):
    out = []
    for question, answer in pairs:
        out.append(conversation.Turn("user", question))
        out.append(conversation.Turn("assistant", answer))
    return out


DEPARTMENTS = _turns(
    ("How many departments are there?", "There are 8 departments."),
)


class FollowupDetectionTests(TestCase):
    """Cheap, deterministic, and biased towards catching follow-ups.

    A false negative degrades to the old behaviour. A false positive costs one
    small LLM call. Neither produces a wrong answer, which is why the bias is
    acceptable.
    """

    def test_catches_bare_pronoun_references(self):
        for q in ["name them", "list them", "what are they", "describe those",
                  "how many of them", "what about it"]:
            self.assertTrue(conversation.looks_like_followup(q), q)

    def test_catches_elliptical_continuations(self):
        for q in ["what about Computer Science", "and Medicine?", "how about Science",
                  "same for Management", "which ones", "just Engineering?"]:
            self.assertTrue(conversation.looks_like_followup(q), q)

    def test_leaves_self_contained_questions_alone(self):
        for q in [
            "How many faculty are in the Engineering department?",
            "What is the tuition fee for Computer Science?",
            "Describe the faculty development profile for Medicine.",
            "How many faculty records come from Deemed universities?",
        ]:
            self.assertFalse(conversation.looks_like_followup(q), q)

    def test_a_long_question_containing_a_pronoun_is_not_a_followup(self):
        """"that" here is a relative pronoun, not a reference to a prior turn.

        Without the length guard this question would trigger a resolution call
        on every ask, for no benefit.
        """
        self.assertFalse(conversation.looks_like_followup(
            "How many faculty are in the department that has the most publications?"
        ))

    def test_empty_input_is_not_a_followup(self):
        self.assertFalse(conversation.looks_like_followup(""))
        self.assertFalse(conversation.looks_like_followup(None))


class DigestTests(TestCase):
    def test_empty_history_produces_no_block_at_all(self):
        """Not a heading with nothing under it.

        An empty "Earlier in this conversation:" section reads to a small model
        as an assertion that nothing came before, which is worse than silence.
        """
        self.assertEqual(conversation.as_prompt_block([]), "")

    def test_the_block_carries_both_sides_of_the_exchange(self):
        block = conversation.as_prompt_block(DEPARTMENTS)
        self.assertIn("User: How many departments are there?", block)
        self.assertIn("Assistant: There are 8 departments.", block)

    def test_verification_appendix_is_stripped_from_history(self):
        """Feeding the machinery back in teaches the model to write more of it."""
        cleaned = conversation._clean_answer(
            "There are 8 departments.\n\n---\n*Note: part of this answer could not "
            "be confirmed against the college records.*"
        )
        self.assertEqual(cleaned, "There are 8 departments.")

    def test_long_answers_are_truncated(self):
        cleaned = conversation._clean_answer("word " * 400)
        self.assertLessEqual(len(cleaned), conversation.ANSWER_CHARS + 2)


class ResolutionTests(TestCase):
    def test_a_followup_is_rewritten_to_stand_alone(self):
        with mock.patch("common.ollama.chat", return_value="Name the 8 departments."):
            resolved, was = conversation.resolve("name them", DEPARTMENTS)
        self.assertTrue(was)
        self.assertEqual(resolved, "Name the 8 departments.")

    def test_no_history_means_no_llm_call_at_all(self):
        with mock.patch("common.ollama.chat") as chat:
            resolved, was = conversation.resolve("name them", [])
        self.assertFalse(chat.called)
        self.assertEqual(resolved, "name them")
        self.assertFalse(was)

    def test_a_self_contained_question_costs_nothing(self):
        """The latency guard. A normal question must not pay for this feature."""
        with mock.patch("common.ollama.chat") as chat:
            resolved, was = conversation.resolve(
                "How many faculty are in the Engineering department?", DEPARTMENTS
            )
        self.assertFalse(chat.called, "a self-contained question triggered a resolve call")
        self.assertEqual(resolved, "How many faculty are in the Engineering department?")
        self.assertFalse(was)

    def test_an_llm_failure_degrades_to_the_original_question(self):
        from common.exceptions import LLMUnavailable
        with mock.patch("common.ollama.chat", side_effect=LLMUnavailable("down")):
            resolved, was = conversation.resolve("name them", DEPARTMENTS)
        self.assertEqual(resolved, "name them")
        self.assertFalse(was)

    def test_a_rewrite_that_is_actually_an_answer_is_rejected(self):
        """The 3B model sometimes answers instead of rewriting.

        Passing "There are 8 departments." downstream as the question would
        send the SQL agent looking for that sentence and would poison the cache
        key with an answer.
        """
        with mock.patch("common.ollama.chat", return_value="There are 8 departments."):
            resolved, was = conversation.resolve("name them", DEPARTMENTS)
        self.assertEqual(resolved, "name them")
        self.assertFalse(was)

    def test_decoration_is_stripped(self):
        with mock.patch("common.ollama.chat",
                        return_value='Rewritten: "Name the 8 departments."'):
            resolved, _ = conversation.resolve("name them", DEPARTMENTS)
        self.assertEqual(resolved, "Name the 8 departments.")

    def test_an_empty_rewrite_falls_back(self):
        with mock.patch("common.ollama.chat", return_value="   "):
            resolved, was = conversation.resolve("name them", DEPARTMENTS)
        self.assertEqual(resolved, "name them")
        self.assertFalse(was)


class HistoryWindowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hist", password="Hist-Pw-4417")
        self.convo = Conversation.objects.create(user=self.user, title="t")

    def _add(self, role, text, route=""):
        return Message.objects.create(
            conversation=self.convo, role=role, text=text, route=route
        )

    def test_window_is_bounded(self):
        """The whole conversation is NOT sent. 20 exchanges must yield 3."""
        for i in range(20):
            self._add("user", f"question {i}")
            self._add("assistant", f"answer {i}")

        turns = conversation.load(self.convo, exchanges=3)

        self.assertEqual(len(turns), 6)
        self.assertIn("19", turns[-1].text)
        self.assertNotIn("question 0", [t.text for t in turns])

    def test_oldest_first(self):
        """Chronological, or the transcript reads backwards to the model."""
        self._add("user", "first")
        self._add("assistant", "second")
        self._add("user", "third")
        turns = conversation.load(self.convo)
        self.assertEqual([t.text for t in turns][:3], ["first", "second", "third"])

    def test_no_conversation_yields_nothing(self):
        self.assertEqual(conversation.load(None), [])

    def test_zero_window_disables_the_feature(self):
        self._add("user", "q")
        self.assertEqual(conversation.load(self.convo, exchanges=0), [])


class CacheIsolationTests(TestCase):
    """Item 5: an ambiguous follow-up must not collide with an unrelated one.

    These build the Context the pipeline builds and assert on the key it would
    use, rather than exercising the cache itself — the property under test is
    that the key carries the conversation, and that is decided in
    prepare_context.
    """

    def setUp(self):
        django_cache.clear()

    def test_the_cache_key_is_the_resolved_question(self):
        with mock.patch("common.ollama.chat", return_value="Name the 8 departments."):
            ctx = service.prepare_context("name them", history_turns=DEPARTMENTS)
        self.assertEqual(ctx.question, "Name the 8 departments.")
        self.assertEqual(ctx.asked, "name them")

    def test_the_same_words_in_two_conversations_get_different_keys(self):
        """THE COLLISION THIS PREVENTS.

        Both users type "name them". Keyed literally they are the same string
        and the second is served the first one's answer.
        """
        courses = _turns(("How many courses are there?", "There are 42 courses."))

        with mock.patch("common.ollama.chat", return_value="Name the 8 departments."):
            a = service.prepare_context("name them", history_turns=DEPARTMENTS)
        with mock.patch("common.ollama.chat", return_value="Name the 42 courses."):
            b = service.prepare_context("name them", history_turns=courses)

        self.assertNotEqual(
            a.question, b.question,
            "two unrelated follow-ups produced the same cache key and would "
            "have served each other's answers",
        )

    def test_a_standalone_question_keys_on_itself_exactly_as_before(self):
        """No cache churn for the 95% case: the key must not change."""
        q = "How many faculty are in the Engineering department?"
        with mock.patch("common.ollama.chat") as chat:
            ctx = service.prepare_context(q, history_turns=DEPARTMENTS)
        self.assertFalse(chat.called)
        self.assertEqual(ctx.question, q)
        self.assertFalse(ctx.resolved)

    def test_no_history_behaves_exactly_as_before_this_feature(self):
        ctx = service.prepare_context("name them")
        self.assertEqual(ctx.question, "name them")
        self.assertEqual(ctx.block, "")
        self.assertFalse(ctx.resolved)


class ContextReachesEveryAgentTests(TestCase):
    """Item 1: the router, SQL, RAG and synthesis must all see the context."""

    def setUp(self):
        django_cache.clear()
        with mock.patch("common.ollama.chat", return_value="Name the 8 departments."):
            self.ctx = service.prepare_context("name them", history_turns=DEPARTMENTS,
                                               previous_route="SQL")

    def test_the_router_receives_the_history_and_the_previous_route(self):
        with mock.patch("orchestrator.service.classify") as classify:
            classify.return_value = mock.Mock(error=None, route="SQL", reason="r")
            service._resolve_route(self.ctx.question, self.ctx)

        kwargs = classify.call_args.kwargs
        self.assertIn("User: How many departments are there?", kwargs["history_block"])
        self.assertEqual(kwargs["previous_route"], "SQL")

    def test_the_sql_agent_receives_the_history(self):
        with mock.patch("orchestrator.service.sql_ask") as sql_ask:
            service._gather_sources(self.ctx.question, "SQL",
                                    history_block=self.ctx.block)
        self.assertIn("How many departments", sql_ask.call_args.kwargs["history_block"])

    def test_retrieval_embeds_the_RESOLVED_text_not_the_pronoun(self):
        """The one thing prompt context cannot fix — see _run_rag."""
        with mock.patch("orchestrator.service.retrieve", return_value=[]) as retrieve:
            service._gather_sources(self.ctx.question, "RAG",
                                    history_block=self.ctx.block)
        embedded = retrieve.call_args.args[0]
        self.assertEqual(embedded, "Name the 8 departments.")
        self.assertNotEqual(embedded, "name them")

    def test_synthesis_receives_the_history(self):
        with mock.patch.object(
            service, "_gather_sources",
            return_value=(None, [], "SQL", [], []),
        ), mock.patch.object(
            service, "_resolve_route", return_value=("SQL", "r")
        ), mock.patch.object(
            service, "synthesize_answer_stream", return_value=iter(["ok"])
        ) as synth, mock.patch.object(
            service.verification, "verify", return_value=("ok", "", {"verification": "off"})
        ):
            list(service._generate_stream(self.ctx.question, context=self.ctx))

        self.assertIn("How many departments", synth.call_args.kwargs["history_block"])
