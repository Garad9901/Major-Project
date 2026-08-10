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
from verification_agent.service import VerdictUnreadable, _parse_claims


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

    def test_declines_when_a_number_is_not_in_the_source(self):
        sql = _SqlResult(rows=[{"count": 3053}], columns=["count"])
        result = fast_check.try_fast_check(
            "q", "There are 9,999 Lecturers.", sql_result=sql
        )
        self.assertFalse(result.decided)
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
