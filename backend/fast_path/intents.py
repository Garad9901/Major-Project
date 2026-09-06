# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Question families answered without a language model.

WHAT MAKES THIS SAFE, AND WHY IT IS NOT A SECOND SQL AGENT

The SQL agent asks a model to WRITE a query, then validates it with the guard
because the model is untrusted. Nothing here writes SQL. Every statement is a
literal in this file, and the only thing the question contributes is a VALUE,
bound as a parameter by the driver.

That difference is the whole security argument:

  * a wrong match produces the wrong ANSWER TO A QUESTION, never a different
    query shape, never a different table, never a second statement
  * the guard's job — "is this SQL safe to run" — cannot fail here because the
    SQL was written by hand and reviewed
  * values are never string-formatted into SQL, so there is nothing to inject
    into

The one thing that IS attacker-influenced is which of these fixed statements
runs and with what value, and both are constrained: the intent must match a
pattern, and the value must already exist in the database's own vocabulary.

WHY EVERY FAMILY IS A COUNT OR AN AVERAGE

Because those have exactly one correct answer that can be rendered without
judgement. "Describe the development profile of Engineering" does not — it needs
prose, and prose is what the model is for. Attempting it here would mean writing
a template that summarises, which is the same act of generation with none of the
model's flexibility and all of its risk of saying something the data does not
support.

Anything not listed here falls through to the model. That is the correct
default, and it is why this file is allowed to be conservative.
"""

import re

# ---------------------------------------------------------------------------
# Patterns
#
# Written to match how people ACTUALLY ask, taken from the audit log rather than
# imagined. The real traffic contains all of:
#
#     How many faculty are in the Computer Science department?
#     How many faculty records are there for the Science department?
#     How Many Faculty members are there in CSE Department
#     How many faculty hold the rank of Professor?
#     How many faculty have Expert competency level?
#     How many faculty are from Public universities?
#
# so the patterns are deliberately loose about the words BETWEEN the anchors and
# strict about the anchors themselves. A pattern that matches too eagerly is not
# a safety problem — it is a wrong answer, which is worse — so each one requires
# a counting verb AND a subject AND a value found in the database vocabulary.
# ---------------------------------------------------------------------------

_COUNT = r"(?:how\s+many|number\s+of|count\s+of|total\s+(?:number\s+of\s+)?)"
_FACULTY = r"(?:faculty|staff|teachers?|lecturers?|academics?)"


class Intent:
    """One question family: how to recognise it, what to run, how to say it.

    `sql` is a format string with ONE placeholder, `{table}`, filled from the
    schema map — never from the question. `{p}` marks parameter positions and is
    replaced with the driver's placeholder style at execution time, so the same
    statement works on psycopg2 (%s) and pyodbc (?).
    """

    def __init__(self, name, pattern, table, sql, slots, template, zero_template=None):
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.table = table
        self.sql = sql
        self.slots = slots          # [(logical_table, column)] the values fill
        self.template = template
        # What to say when the count is legitimately zero. Distinct from the
        # normal template because "There are 0 faculty in X" reads as a data
        # error to a reader, and because this system's founding rule is that a
        # real zero and a failed lookup must never look the same.
        self.zero_template = zero_template or template


INTENTS = [
    Intent(
        name="faculty_count_by_department",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\bdepartment\b|"
                rf"{_COUNT}\s+{_FACULTY}\s+records?\b.*\bfor\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE department = {p}",
        slots=[("faculty_development", "department")],
        template="There are {n:,} faculty in the {v0} department.",
        zero_template="No faculty in the college records are listed under the {v0} department.",
    ),
    Intent(
        name="faculty_count_by_rank",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\b(?:rank|hold|designated)\b|"
                rf"{_COUNT}\s+(?:professors?|lecturers?|associate|assistant)\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE academic_rank = {p}",
        slots=[("faculty_development", "academic_rank")],
        template="There are {n:,} faculty at the rank of {v0}.",
        zero_template="No faculty in the college records hold the rank of {v0}.",
    ),
    Intent(
        name="faculty_count_by_competency",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\bcompetenc",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE competency_level = {p}",
        slots=[("faculty_development", "competency_level")],
        template="There are {n:,} faculty at {v0} competency level.",
        zero_template="No faculty in the college records are at {v0} competency level.",
    ),
    Intent(
        name="faculty_count_by_university_type",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\buniversit",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE university_type = {p}",
        slots=[("faculty_development", "university_type")],
        template="There are {n:,} faculty from {v0} universities.",
        zero_template="No faculty in the college records come from {v0} universities.",
    ),
    Intent(
        name="faculty_count_by_department_and_rank",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\bdepartment\b.*\brank\b|"
                rf"{_COUNT}\s+{_FACULTY}\b.*\bin\b.*\bwith\b.*\brank\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE department = {p} AND academic_rank = {p}",
        slots=[("faculty_development", "department"), ("faculty_development", "academic_rank")],
        template="There are {n:,} {v1} faculty in the {v0} department.",
        zero_template="No {v1} faculty in the college records are listed under {v0}.",
    ),
    Intent(
        name="faculty_count_by_department_and_competency",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\bdepartment\b.*\bcompetenc",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE department = {p} AND competency_level = {p}",
        slots=[("faculty_development", "department"), ("faculty_development", "competency_level")],
        template="There are {n:,} faculty in the {v0} department at {v1} competency level.",
        zero_template="No faculty in the {v0} department are at {v1} competency level.",
    ),
    Intent(
        name="faculty_count_total",
        pattern=rf"^{_COUNT}\s+{_FACULTY}\s+(?:are\s+there|in\s+total|records?\s+are\s+there)\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table}",
        slots=[],
        template="There are {n:,} faculty in the college records.",
        zero_template="The faculty records are empty.",
    ),
    Intent(
        name="faculty_count_by_development_need",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\b(?:development\s+need|target)\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE target = {p}",
        slots=[("faculty_development", "target")],
        template="There are {n:,} faculty assessed as {v0}.",
        zero_template="No faculty in the college records are assessed as {v0}.",
    ),
    Intent(
        name="faculty_count_by_lms_usage",
        pattern=rf"{_COUNT}\s+{_FACULTY}\b.*\blms\b|{_COUNT}\s+{_FACULTY}\b.*\blearning\s+management\b",
        table="faculty_development",
        sql="SELECT COUNT(*) AS n FROM {table} WHERE lms_usage_frequency = {p}",
        slots=[("faculty_development", "lms_usage_frequency")],
        template="There are {n:,} faculty whose LMS usage is recorded as {v0}.",
        zero_template="No faculty in the college records have LMS usage recorded as {v0}.",
    ),
    Intent(
        name="department_count",
        # Anchored to the START so "how many faculty are in the X department"
        # cannot reach it. That question also contains "how many" and
        # "department", and answering it with the number of DEPARTMENTS would be
        # a confidently wrong small number.
        pattern=rf"^\s*{_COUNT}\s+departments?\b",
        table="departments",
        sql="SELECT COUNT(*) AS n FROM {table}",
        slots=[],
        template="The college has {n:,} departments.",
        zero_template="No departments are recorded in the college records.",
    ),
]

# ---------------------------------------------------------------------------
# AVERAGES
#
# Separate from the counting families because the rendering differs: a count is
# an integer and an average is not, and "67.19999999" is not an answer anyone
# wants. Held to one decimal place, which is the precision the underlying scores
# are recorded at.
#
# The phrase -> column mapping is EXPLICIT and small. It is not inferred from
# column names: "research productivity score" and "research publications" are
# different columns and a fuzzy match between them returns a plausible wrong
# number, which is the one outcome this module exists to avoid. A metric not
# listed here goes to the model.
# ---------------------------------------------------------------------------

AVERAGE_METRICS = {
    "research publications": ("research_publications", "research publications per faculty member", 1),
    "teaching effectiveness": ("teaching_effectiveness_score", "teaching effectiveness score", 1),
    "student feedback": ("student_feedback_score", "student feedback score", 1),
    "ai tool adoption": ("ai_tool_adoption_score", "AI tool adoption score", 1),
    "data literacy": ("data_literacy_score", "data literacy score", 1),
    "big data readiness": ("big_data_readiness_score", "big data readiness score", 1),
    "digital tool usage": ("digital_tool_usage_score", "digital tool usage score", 1),
    "overall faculty development index": ("overall_faculty_development_index", "overall faculty development index", 1),
    "collaboration index": ("collaboration_index", "collaboration index", 1),
    "professional development": ("professional_development_score", "professional development score", 1),
    "innovation in teaching": ("innovation_in_teaching_score", "innovation in teaching score", 1),
    "age": ("age", "age", 1),
}

_AVERAGE_RE = re.compile(
    r"\b(?:average|mean|avg)\b", re.IGNORECASE
)

# Ordered longest-first at match time: a question naming BOTH a department and a
# rank must reach the two-slot intent, not the one-slot department intent that
# would also match it and quietly drop half the question. That ordering is a
# correctness property, not a performance one — see test_fast_path.py.
INTENTS.sort(key=lambda i: -len(i.slots))
