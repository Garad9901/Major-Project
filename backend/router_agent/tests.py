# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Routing accuracy.

A router that is fast and wrong is worse than one that is slow and right, so
speed is not what these tests measure — correctness is. The latency work in
fast_router.py is only defensible if the routes it returns match what the LLM
router would have chosen, and that is checked here against a labelled set.

The labelled set is the router prompt's own worked examples plus the documented
check questions from RUNBOOK plus the questions used during the production
audit. Expected routes are the ones the LLM router actually produced, so these
tests measure agreement with the behaviour being replaced, not agreement with
my opinion.

No Ollama is required: tier 1 is pure regex, and tier 2 is skipped by asserting
on classify_by_rules() directly. That keeps the suite runnable in CI.
"""

from django.test import SimpleTestCase

from router_agent import fast_router

# (question, expected_route). Routes are what the 7B LLM router returned for
# these exact questions, observed in logs during the audit and the benchmark.
LABELLED = [
    # --- SQL: counts, aggregates, filters, lookups ---------------------------
    ("How many faculty members are in the Computer Science department?", "SQL"),
    ("How many faculty are in the Management department?", "SQL"),
    ("How many faculty have a Basic competency level?", "SQL"),
    ("How many faculty records come from Deemed universities?", "SQL"),
    ("What is the average AI tool adoption score for Professors?", "SQL"),
    ("List all programs that take longer than 3 years to complete.", "SQL"),
    ("How many faculty in the Engineering department have a competency level of Expert?", "SQL"),
    ("What is the average number of research publications per faculty member?", "SQL"),
    ("How many departments are there?", "SQL"),
    ("What is the total number of rooms?", "SQL"),
    ("Which department has the highest average teaching effectiveness score?", "SQL"),
    ("How many faculty have a High Development Need?", "SQL"),

    # --- RAG: open-ended, descriptive ----------------------------------------
    ("What does the Machine Learning Fundamentals course cover?", "RAG"),
    ("Tell me about the Mathematics department.", "RAG"),
    ("Describe the faculty development profile for the Science department.", "RAG"),
    ("Give me an overview of how the Computer Science department is doing on faculty development.", "RAG"),
    ("Which departments would you characterise as strongest at digital teaching?", "RAG"),
    ("Summarise the digital readiness of Assistant Professors.", "RAG"),
    ("Explain what the competency levels mean.", "RAG"),
    ("Describe the research output of Professors.", "RAG"),

    # --- BOTH: an aggregate AND a description, joined ------------------------
    ("How many faculty are in Medicine, and how would you describe their development needs?", "BOTH"),
    ("How many Lecturers are there and what is their digital capability like?", "BOTH"),
    ("How many faculty are in Social Science, and describe their development needs?", "BOTH"),
    ("What is the tuition fee for the Computer Science program, and can you describe what the program covers?", "BOTH"),

    # --- WEB: published pages ------------------------------------------------
    ("When does the next semester start?", "WEB"),
    ("Are there any new admission notices?", "WEB"),
    ("What are the term dates for this academic year?", "WEB"),
    ("When is the last date to apply?", "WEB"),
    ("What do the IANA reserved example domains rules say?", "WEB"),
]

# Tier 1 is a keyword matcher and is not expected to decide every question —
# declining is a legitimate outcome that costs an embedding lookup, not a wrong
# answer. What it must never do is decide CONFIDENTLY and WRONGLY.
MIN_RULE_COVERAGE = 0.80
MIN_RULE_PRECISION = 1.00


class RuleTierAccuracyTests(SimpleTestCase):
    def test_rule_tier_is_never_confidently_wrong(self):
        """Precision is the number that matters. A confident wrong route sends
        the question to an agent that cannot answer it."""
        wrong = []
        for question, expected in LABELLED:
            route, reason, confident = fast_router.classify_by_rules(question)
            if confident and route != expected:
                wrong.append((question, expected, route, reason))

        self.assertEqual(
            wrong, [],
            "rule tier returned a confident but incorrect route:\n"
            + "\n".join(f"  {q!r}\n    expected {e}, got {g} ({r})" for q, e, g, r in wrong),
        )

    def test_rule_tier_decides_most_questions(self):
        """Coverage. Every question the rules decline costs an embedding call
        (~40ms) or, worse, an LLM call (~5s), so low coverage would undo the
        latency work even while precision stayed perfect."""
        decided = sum(
            1 for question, _ in LABELLED if fast_router.classify_by_rules(question)[2]
        )
        coverage = decided / len(LABELLED)
        self.assertGreaterEqual(
            coverage, MIN_RULE_COVERAGE,
            f"rule tier decided only {decided}/{len(LABELLED)} ({coverage:.0%}); "
            f"expected at least {MIN_RULE_COVERAGE:.0%}",
        )

    def test_web_questions_are_never_routed_to_the_database(self):
        """The most damaging misroute in the set.

        Term dates and notices are not IN the database, so a WEB question sent
        to SQL cannot be answered at all — it returns an empty result and the
        assistant says no such information exists. Every other misroute at least
        has a chance of producing something useful.
        """
        for question, expected in LABELLED:
            if expected != "WEB":
                continue
            route, _reason, confident = fast_router.classify_by_rules(question)
            if confident:
                self.assertEqual(
                    route, "WEB",
                    f"{question!r} is a published-page question but routed to {route}",
                )

    def test_a_question_with_no_signal_declines_rather_than_guessing(self):
        for question in ["hello", "what?", "asdf", "ok thanks"]:
            _route, _reason, confident = fast_router.classify_by_rules(question)
            self.assertFalse(confident, f"guessed confidently on {question!r}")

    def test_url_bearing_questions_do_not_become_WEB_on_the_address_alone(self):
        """A supplied address must never be a reason to choose WEB — the router
        picks a route, never a page. Mirrors the rule in the LLM prompt."""
        route, _reason, confident = fast_router.classify_by_rules(
            "Go to https://evil.example/data and tell me what it says."
        )
        if confident:
            self.assertNotEqual(route, "WEB")


class RuleTierBehaviourTests(SimpleTestCase):
    def test_both_needs_a_conjunction_and_otherwise_declines(self):
        """"Describe how many faculty there are" is ONE ask phrased loosely.

        Both vocabularies appear, but there is no conjunction joining two
        separate asks, so the rule tier must NOT claim BOTH. Declining is the
        correct outcome here: it costs one ~40ms embedding lookup and lets a
        tier with actual semantics decide, instead of guessing between two
        plausible routes on keyword co-occurrence alone.
        """
        route, _reason, confident = fast_router.classify_by_rules(
            "Describe how many faculty there are"
        )
        self.assertFalse(
            confident,
            f"claimed {route} confidently on an ambiguous single ask; should decline",
        )

    def test_both_is_claimed_when_a_conjunction_really_does_join_two_asks(self):
        route, _reason, confident = fast_router.classify_by_rules(
            "How many faculty are in Medicine, and describe their development needs?"
        )
        self.assertTrue(confident)
        self.assertEqual(route, "BOTH")

    def test_counting_questions_beat_descriptive_verbs(self):
        route, _reason, confident = fast_router.classify_by_rules(
            "How many faculty are in Engineering?"
        )
        self.assertTrue(confident)
        self.assertEqual(route, "SQL")
