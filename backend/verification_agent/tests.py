# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The verification fast path, and the terse verdict parser.

MOST OF THESE TESTS ASSERT THAT THE FAST PATH DECLINES.

That is the point. A fast path for a safety check is only worth having if it is
provably conservative: the failure that matters is not "it was slow", it is "it
said an answer was fine without checking it". Every test below that expects
`decided is False` is guarding a way that could happen.
"""

from django.test import SimpleTestCase

from verification_agent import fast_check
from verification_agent.fast_check import try_fast_check
from verification_agent.service import (
    REFUTED_MESSAGE,
    VerdictUnreadable,
    _parse_claims,
)


class _SqlResult:
    def __init__(self, rows=None, columns=None, error=None, generated_sql="SELECT 1"):
        self.rows = rows or []
        self.columns = columns or []
        self.error = error
        self.generated_sql = generated_sql


class _Chunk:
    def __init__(self, text, table="faculty_development_profiles", row_id=1, score=0.9):
        self.text = text
        self.table = table
        self.row_id = row_id
        self.score = score


class FastPathAcceptsTests(SimpleTestCase):
    def test_a_simple_count_answer_is_matched_without_an_llm(self):
        sql = _SqlResult(rows=[{"count": 3053}], columns=["count"])
        result = fast_check.try_fast_check(
            "How many Lecturers are there?",
            "There are 3,053 faculty members holding the Lecturer rank.",
            sql_result=sql,
        )
        self.assertTrue(result.decided, result.reason)
        self.assertEqual(len(result.claims), 1)
        self.assertTrue(all(c["supported"] for c in result.claims))

    def test_thousands_separators_do_not_defeat_matching(self):
        sql = _SqlResult(rows=[{"n": 13000}], columns=["n"])
        result = fast_check.try_fast_check("q", "There are 13,000 records.", sql_result=sql)
        self.assertTrue(result.decided, result.reason)

    def test_display_rounding_is_accepted(self):
        """67.20 stored, 67.2 written. Legitimate, and must not force an LLM call."""
        sql = _SqlResult(rows=[{"avg": 67.20}], columns=["avg"])
        result = fast_check.try_fast_check("q", "The average is 67.2.", sql_result=sql)
        self.assertTrue(result.decided, result.reason)

    def test_numbers_sourced_from_a_rag_passage_match(self):
        chunk = _Chunk("The overall faculty development index averages 67.2 out of 100.")
        result = fast_check.try_fast_check(
            "q", "The index averages 67.2 out of 100.", rag_chunks=[chunk]
        )
        self.assertTrue(result.decided, result.reason)


class FastPathDeclinesTests(SimpleTestCase):
    """Each of these is a way the fast path could wrongly bless a bad answer."""

    def test_a_contradicted_scalar_now_REFUTES_rather_than_declining(self):
        """BEHAVIOUR CHANGED HERE, deliberately — see audit log entry 801.

        This used to assert `decided is False` with reason "not found in
        source", i.e. the fast path declined and the LLM tier took over. That
        decline is what let a fabricated figure reach a user: the LLM tier timed
        out and the answer shipped hedged.

        Against a SINGLE-SCALAR source the contradiction is not ambiguous, so it
        is now a refutation. The test's original intent — the fast path must
        never wrongly bless a bad answer — holds more strongly than before: it
        no longer merely abstains, it rejects.
        """
        sql = _SqlResult(rows=[{"count": 3053}], columns=["count"])
        result = fast_check.try_fast_check(
            "q", "There are 9,999 Lecturers.", sql_result=sql
        )
        self.assertFalse(result.decided, "must never be treated as confirmed")
        self.assertTrue(result.refuted)

    def test_still_declines_when_the_source_is_not_a_single_scalar(self):
        """The decline path is not gone, only narrowed. With more than one row
        there is no single figure the answer was obliged to state, so an
        unmatched number is genuinely 'cannot tell' and belongs to the LLM."""
        sql = _SqlResult(rows=[{"n": 2073}, {"n": 1046}], columns=["n"])
        result = fast_check.try_fast_check(
            "q", "There are 9,999 faculty altogether.", sql_result=sql
        )
        self.assertFalse(result.decided)
        self.assertFalse(result.refuted)
        self.assertIn("not found in source", result.reason)

    def test_adjacent_integers_are_not_confused(self):
        """730 vs 731 must not pass as a rounding difference."""
        sql = _SqlResult(rows=[{"count": 731}], columns=["count"])
        result = fast_check.try_fast_check("q", "There are 730 faculty.", sql_result=sql)
        self.assertFalse(result.decided, "730 was accepted against a source value of 731")

    def test_declines_on_an_invented_person(self):
        """The exact failure seen in the production audit: with no data, the
        model wrote "Dr. Jane Smith and Professor John Doe". Numeric matching
        alone would not catch it, because the numbers present were fine."""
        chunk = _Chunk("Professors average 7.19 publications each.")
        result = fast_check.try_fast_check(
            "Who publishes most?",
            "Jane Smith and John Doe lead with 7.19 publications on average.",
            rag_chunks=[chunk],
        )
        self.assertFalse(result.decided)
        self.assertIn("proper noun", result.reason)

    def test_declines_when_the_answer_has_no_numbers(self):
        chunk = _Chunk("The department is strong on digital teaching.")
        result = fast_check.try_fast_check(
            "q", "The department is generally strong in this area.", rag_chunks=[chunk]
        )
        self.assertFalse(result.decided)
        self.assertIn("no numeric claims", result.reason)

    def test_declines_when_the_sql_query_errored(self):
        """The audit's worst finding lives here: a failed lookup being described
        as an absence. That is a judgement call and must reach the LLM."""
        sql = _SqlResult(error='column "x" does not exist')
        result = fast_check.try_fast_check(
            "q", "There are 0 matching records.", sql_result=sql
        )
        self.assertFalse(result.decided)
        self.assertIn("judgement", result.reason)

    def test_declines_on_a_long_answer(self):
        sql = _SqlResult(rows=[{"count": 42}], columns=["count"])
        long_answer = "There are 42 faculty. " + ("Additional prose. " * 80)
        result = fast_check.try_fast_check("q", long_answer, sql_result=sql)
        self.assertFalse(result.decided)
        self.assertIn("too long", result.reason)

    def test_declines_when_there_is_no_source_at_all(self):
        result = fast_check.try_fast_check("q", "There are 42 faculty.")
        self.assertFalse(result.decided)

    def test_never_raises_on_malformed_input(self):
        for answer in [None, "", "   ", "\x00\x01"]:
            result = fast_check.try_fast_check("q", answer, sql_result=_SqlResult())
            self.assertFalse(result.decided)


class TerseVerdictParsingTests(SimpleTestCase):
    """The verifier now reports only problems. Both shapes must parse, because
    a model does not always obey a changed instruction first time and silently
    reading zero claims would look like a clean pass."""

    def test_new_shape_clean_run(self):
        claims, checked = _parse_claims('{"checked": 13, "unsupported": []}')
        self.assertEqual(claims, [])
        self.assertEqual(checked, 13)

    def test_new_shape_with_a_flagged_claim(self):
        raw = ('{"checked": 5, "unsupported": [{"text": "there are 9999 faculty", '
               '"confidence": 0.9, "evidence": "source says 3053", "correct_value": "3053"}]}')
        claims, checked = _parse_claims(raw)
        self.assertEqual(checked, 5)
        self.assertEqual(len(claims), 1)
        self.assertFalse(claims[0]["supported"])
        self.assertEqual(claims[0]["correct_value"], "3053")

    def test_old_shape_still_parses(self):
        raw = ('{"claims": [{"text": "a", "supported": true, "confidence": 1.0, '
               '"evidence": "e", "correct_value": null}, '
               '{"text": "b", "supported": false, "confidence": 0.8, '
               '"evidence": "e2", "correct_value": null}]}')
        claims, checked = _parse_claims(raw)
        self.assertEqual(checked, 2)
        self.assertEqual(len(claims), 2)
        self.assertEqual([c["supported"] for c in claims], [True, False])

    def test_unparseable_output_raises_rather_than_looking_clean(self):
        """The defect this guards against was live in production.

        A verdict truncated mid-string by the output cap used to return an empty
        claim list, which is indistinguishable from "checked, nothing wrong" —
        so the answer was logged `verification=ran, flagged=0` and shown to the
        user as though it had passed a check that never completed.
        """
        with self.assertRaises(VerdictUnreadable):
            _parse_claims("not json at all")

    def test_truncated_json_raises(self):
        """The exact shape seen in the logs: valid JSON that stops mid-string."""
        truncated = (
            '{"checked": 5, "unsupported": [{"text": "a claim", "confidence": 1.0, '
            '"evidence": "the source passage begins here and then just st'
        )
        with self.assertRaises(VerdictUnreadable):
            _parse_claims(truncated)

    def test_non_object_json_raises(self):
        for raw in ["[1, 2, 3]", '"a string"', "42"]:
            with self.subTest(raw=raw):
                with self.assertRaises(VerdictUnreadable):
                    _parse_claims(raw)

    def test_code_fenced_json_parses(self):
        claims, checked = _parse_claims('```json\n{"checked": 3, "unsupported": []}\n```')
        self.assertEqual(checked, 3)
        self.assertEqual(claims, [])


class CorrectionOnlyWhenCorrectableTests(SimpleTestCase):
    """A claim flagged with correct_value=null means "could not confirm", not
    "this is wrong". Rewriting on that basis let a 3B model replace a correct
    figure with the literal placeholder "[The actual number of faculty in
    Management]" — measured, not hypothetical.
    """

    def test_flagged_without_a_correct_value_is_not_correctable(self):
        claims, _checked = _parse_claims(
            '{"checked": 2, "unsupported": [{"text": "mean age is 58.71", '
            '"confidence": 0.8, "evidence": "not in source", "correct_value": null}]}'
        )
        correctable = [c for c in claims if c.get("correct_value")]
        self.assertEqual(correctable, [], "would have triggered a pointless rewrite")

    def test_flagged_with_a_correct_value_is_correctable(self):
        claims, _checked = _parse_claims(
            '{"checked": 2, "unsupported": [{"text": "there are 9999 faculty", '
            '"confidence": 0.9, "evidence": "source says 3053", "correct_value": "3053"}]}'
        )
        correctable = [c for c in claims if c.get("correct_value")]
        self.assertEqual(len(correctable), 1)
        self.assertEqual(correctable[0]["correct_value"], "3053")

    def test_empty_string_correct_value_is_not_correctable(self):
        """An empty string is the model declining, not a value."""
        claims, _checked = _parse_claims(
            '{"checked": 1, "unsupported": [{"text": "x", "confidence": 0.5, '
            '"evidence": "e", "correct_value": ""}]}'
        )
        self.assertEqual([c for c in claims if c.get("correct_value")], [])


class ScalarRefutationTests(SimpleTestCase):
    """The narrow refute rule, from audit log entry 801.

    Handed one row `{'count': 2}`, synthesis wrote "There are 2,014 faculty in
    the Computer Science department." fast_check found 2014 absent from the
    source and returned "I cannot tell" — discarding the evidence at the point
    it was strongest. The LLM tier then timed out and the fabrication shipped
    with a hedge.
    """

    def _sql(self, rows, columns=None, error=None):
        class R:
            pass
        r = R()
        r.rows = rows
        r.columns = columns or ["count"]
        r.error = error
        r.generated_sql = "SELECT COUNT(*) FROM faculty_development"
        return r

    # --- the case that prompted this ----------------------------------------

    def test_entry_801_is_refuted(self):
        result = try_fast_check(
            "How many faculty are in the Computer Science department?",
            "There are 2,014 faculty in the Computer Science department.",
            sql_result=self._sql([{"count": 2}]),
        )
        self.assertTrue(result.refuted)
        self.assertFalse(result.decided)

    def test_a_matching_scalar_is_not_refuted(self):
        result = try_fast_check(
            "How many faculty hold the Lecturer rank?",
            "There are 3,053 faculty members holding the Lecturer rank.",
            sql_result=self._sql([{"count": 3053}]),
        )
        self.assertFalse(result.refuted)

    def test_thousands_separators_do_not_cause_a_false_refutation(self):
        """1,916 in the answer is 1916 in the row. A normaliser bug here would
        suppress correct answers, which is the expensive direction."""
        for written in ("1,916", "1916"):
            with self.subTest(written=written):
                result = try_fast_check(
                    "How many faculty are in Computer Science?",
                    f"There are {written} faculty in Computer Science.",
                    sql_result=self._sql([{"count": 1916}]),
                )
                self.assertFalse(result.refuted, written)

    # --- entry conditions: everything below must NOT refute -----------------

    def test_multiple_rows_do_not_refute(self):
        """Only an unambiguous single scalar. A breakdown has no one figure the
        answer must state."""
        result = try_fast_check(
            "Faculty per department?",
            "Engineering has 2,073 and Medicine has 1,046.",
            sql_result=self._sql([{"n": 2073}, {"n": 1046}]),
        )
        self.assertFalse(result.refuted)

    def test_multiple_columns_do_not_refute(self):
        result = try_fast_check(
            "How many Expert faculty in CS and their mean age?",
            "There are 134, with a mean age of 58.71.",
            sql_result=self._sql([{"count": 134, "mean_age": 58.71}],
                                 columns=["count", "mean_age"]),
        )
        self.assertFalse(result.refuted)

    def test_a_failed_lookup_never_refutes(self):
        """A failed lookup is not evidence of anything. Refuting against one
        would turn an outage into an accusation of fabrication."""
        result = try_fast_check(
            "How many faculty?",
            "There are 1,916 faculty.",
            sql_result=self._sql(None, error="connection refused"),
        )
        self.assertFalse(result.refuted)

    def test_no_numbers_in_the_answer_does_not_refute(self):
        result = try_fast_check(
            "How many faculty are in Chemistry?",
            "The college records do not cover that.",
            sql_result=self._sql([{"count": 0}]),
        )
        self.assertFalse(result.refuted)

    def test_a_boolean_cell_is_not_a_measurement(self):
        """bool is an int subclass in Python; a True/False cell must not be
        compared against a count."""
        result = try_fast_check(
            "Is the Engineering department active?",
            "Yes, it has 2,073 faculty.",
            sql_result=self._sql([{"active": True}], columns=["active"]),
        )
        self.assertFalse(result.refuted)

    def test_derived_arithmetic_is_safe_when_the_base_is_stated(self):
        """"None match" rather than "any differs" is what makes this safe: the
        answer states the retrieved figure alongside the derived one."""
        result = try_fast_check(
            "How many faculty are in Computer Science?",
            "There are 1,916 faculty in Computer Science, about 15% of the college.",
            sql_result=self._sql([{"count": 1916}]),
        )
        self.assertFalse(result.refuted)

    def test_a_long_answer_is_still_refuted(self):
        """The confirm path's length cap is deliberately NOT inherited: a
        fabricated count is just as wrong inside a long answer, and the
        comparison is exact either way."""
        long_answer = ("There are 2,014 faculty in the Computer Science department. "
                       + "Additional descriptive prose. " * 40)
        self.assertGreater(len(long_answer), 700)
        result = try_fast_check(
            "How many faculty are in the Computer Science department?",
            long_answer,
            sql_result=self._sql([{"count": 2}]),
        )
        self.assertTrue(result.refuted)


class RefutationNeverSubstitutesTests(SimpleTestCase):
    """THE BOUNDARY, and the reason the whole rule is suppress-only.

    In entry 801 the query returned 2 because it had counted an 11-row staff
    directory; the true answer was 1,916. Auto-correcting 2,014 to 2 would have
    shipped "There are 2 faculty in Computer Science" marked CONFIRMED — a
    confident wrong answer, strictly worse than the hedged fabrication, because
    the hedge was the only thing making a reader doubt it.

    Verification can say "this figure is unsupported". It cannot say "this other
    figure is right", because it cannot see that the evidence came from the
    wrong table.
    """

    def test_the_message_contains_no_digits_at_all(self):
        import re
        self.assertIsNone(
            re.search(r"\d", REFUTED_MESSAGE),
            "the suppression message must not contain a number — not the "
            "fabricated one and not the retrieved one",
        )

    def test_the_message_does_not_leak_either_figure(self):
        self.assertNotIn("2,014", REFUTED_MESSAGE)
        self.assertNotIn("2014", REFUTED_MESSAGE)
        self.assertNotIn("1,916", REFUTED_MESSAGE)

    def test_the_message_tells_the_user_what_to_do(self):
        """"Something went wrong" sends the user away with nothing."""
        self.assertIn("college office", REFUTED_MESSAGE.lower())

    def test_the_refutation_string_is_for_operators_not_users(self):
        """It names both figures, so it must never be what the user sees."""
        result = try_fast_check(
            "How many faculty are in the Computer Science department?",
            "There are 2,014 faculty in the Computer Science department.",
            sql_result=type("R", (), {
                "rows": [{"count": 2}], "columns": ["count"],
                "error": None, "generated_sql": "SELECT 1",
            })(),
        )
        self.assertTrue(result.refuted)
        self.assertIn("2", result.refutation)
        self.assertNotEqual(result.refutation, REFUTED_MESSAGE)
