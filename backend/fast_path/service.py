# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Answer the common question families without a language model.

    try_answer(question) -> FastAnswer | None

None means "not handled here", and the caller runs the normal pipeline. That is
the default for anything this module is not certain about, and being certain is
deliberately hard: the question must match one family's pattern, every value it
names must already exist in the database's own vocabulary, and no other family
may match it as well.

WHY "NONE" RATHER THAN A BEST GUESS
A fast path that answers 95% correctly is worse than one that answers 60% of
questions and declines the rest, because the 5% arrive as confident wrong
figures with no model and no verifier between them and the reader. Declining
costs a slow answer. Guessing costs a wrong one.

WHAT IS PRESERVED FROM THE SLOW PATH
  * a failed lookup is reported as a failure, never as "no such record" — the
    founding rule of this system. A database error here returns None so the
    normal pipeline runs and produces its own degradation message; it never
    renders "there are 0".
  * a genuine zero says so in words chosen for a zero, and is never dressed up
    as an absence of data.
  * the audit log still records the question, the SQL and the answer, because
    the caller logs it exactly as it logs a model-generated one.
"""

import logging
import re
import time

from common import schema_map

from . import entities
from .intents import AVERAGE_METRICS, INTENTS, _AVERAGE_RE

logger = logging.getLogger("fast_path")


class FastAnswer:
    __slots__ = ("text", "intent", "sql", "params", "rows", "elapsed_ms")

    def __init__(self, text, intent, sql, params, rows, elapsed_ms):
        self.text = text
        self.intent = intent
        self.sql = sql
        self.params = params
        self.rows = rows
        self.elapsed_ms = elapsed_ms


def _find_values(question, slots, vocab):
    """Resolve each slot to a value the DATABASE actually contains.

    Longest match first, so "Computer Science" is not resolved as "Science".
    That is a correctness property: both are real departments here, and the
    shorter one is a substring of the longer.

    Returns None if any slot cannot be filled, or if a slot is ambiguous.
    """
    lowered = question.lower()
    values = []
    consumed = []  # (start, end) spans already claimed by an earlier slot

    for logical_table, column in slots:
        candidates = vocab.get((logical_table, column))
        if not candidates:
            return None

        best = None
        for candidate in sorted(candidates, key=len, reverse=True):
            # Word-boundary match, so "Education" does not match inside
            # "Co-Education" and "Arts" does not match inside "Martial Arts".
            for m in re.finditer(rf"\b{re.escape(candidate.lower())}\b", lowered):
                span = (m.start(), m.end())
                if any(span[0] < e and s < span[1] for s, e in consumed):
                    continue  # already claimed by a longer value in another slot
                best = (candidate, span)
                break
            if best:
                break

        if best is None:
            return None
        values.append(best[0])
        consumed.append(best[1])

    return values


def _try_average(question, vocab, conn_factory):
    """"What is the average teaching effectiveness score?" and its relatives.

    Handled apart from the counting families because the rendering differs — an
    average is not an integer, and "67.19999999" is not an answer.

    The phrase -> column mapping is explicit and small (see AVERAGE_METRICS).
    Longest phrase first, so "research publications" is not resolved by a
    shorter overlapping key. A metric that is not listed goes to the model
    rather than being guessed at: "research productivity score" and "research
    publications" are different columns, and a fuzzy match between them returns
    a plausible wrong number.
    """
    if not _AVERAGE_RE.search(question):
        return None

    lowered = question.lower()
    metric = None
    for phrase in sorted(AVERAGE_METRICS, key=len, reverse=True):
        # WORD BOUNDARIES, not `phrase in lowered`.
        #
        # "age" is a substring of "average", so a plain containment test matched
        # the age column for EVERY question containing the word "average".
        # Longest-first ordering hid it whenever a real metric was named, and it
        # surfaced only on an unlisted metric — caught by
        # test_an_unlisted_metric_falls_through, which is what that test is for.
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            metric = (phrase,) + AVERAGE_METRICS[phrase]
            break
    if metric is None:
        return None
    _phrase, column, noun, places = metric

    # An optional department filter, so "average teaching effectiveness in
    # Engineering" is answered about Engineering rather than the whole college —
    # which would be a wrong answer wearing the right words.
    department = None
    for candidate in sorted(vocab.get(("faculty_development", "department"), []), key=len, reverse=True):
        # Word boundary, same as _find_values. Without it "Science" matches
        # inside "Computer Science". The longest-first ordering happens to
        # save it here, but relying on ordering for a property a boundary
        # states directly is how it breaks later.
        if re.search(rf"\b{re.escape(candidate.lower())}\b", lowered):
            department = candidate
            break

    physical_column = schema_map.physical_column("faculty_development", column)
    table = schema_map.physical(intents_table(), qualified=True)

    started = time.perf_counter()
    try:
        with conn_factory() as conn:
            placeholder = _placeholder_style(conn)
            # Column and table come from the map and from AVERAGE_METRICS, both
            # allowlists in code. Only the department VALUE is bound.
            sql = f"SELECT AVG(CAST({physical_column} AS FLOAT)) AS a FROM {table}"
            params = ()
            if department is not None:
                sql += f" WHERE department = {placeholder}"
                params = (department,)
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                row = cur.fetchone()
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("fast path average failed (%s) — deferring to the model", exc)
        return None

    if row is None or row[0] is None:
        # No rows matched, so there is no average. Not renderable as 0 — a mean
        # of nothing is not zero — so this goes to the model.
        return None

    value = round(float(row[0]), places)
    elapsed_ms = (time.perf_counter() - started) * 1000
    where = f" in the {department} department" if department else " across the college"
    text = f"The average {noun}{where} is {value:,.{places}f}."
    logger.info("fast path HIT intent=average_%s dept=%r %.1fms", column, department, elapsed_ms)
    return FastAnswer(
        text=text, intent=f"average_{column}", sql=sql, params=params,
        rows=[{"a": value}], elapsed_ms=elapsed_ms,
    )


def intents_table():
    """The logical table the averages are computed over."""
    return "faculty_development"


def _placeholder_style(conn):
    """psycopg2 wants %s, pyodbc wants ?. Asked of the driver, not assumed."""
    module = type(conn).__module__ or ""
    return "?" if "pyodbc" in module else "%s"


def try_answer(question, conn_factory):
    """A deterministic answer, or None to let the normal pipeline run."""
    if not question or not question.strip():
        return None

    vocab = entities.vocabulary(conn_factory)
    if vocab is None:
        # UNAVAILABLE, not empty. Deferring to the model is the correct
        # degradation; answering from an empty vocabulary would not be.
        return None

    average = _try_average(question, vocab, conn_factory)
    if average is not None:
        return average

    matched = [i for i in INTENTS if i.pattern.search(question)]
    if not matched:
        return None

    # INTENTS is sorted by slot count descending, so the most specific family
    # that matches wins. A question naming a department AND a rank must not be
    # answered by the department-only family, which would silently drop half of
    # what was asked and return a larger, wrong number.
    for intent in matched:
        values = _find_values(question, intent.slots, vocab)
        if values is None:
            continue

        started = time.perf_counter()
        try:
            table = schema_map.physical(intent.table, qualified=True)
            with conn_factory() as conn:
                placeholder = _placeholder_style(conn)
                sql = intent.sql.format(table=table, p=placeholder)
                cur = conn.cursor()
                try:
                    cur.execute(sql, tuple(values))
                    row = cur.fetchone()
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
        except Exception as exc:
            # A FAILED LOOKUP IS NOT AN ABSENCE OF RECORDS.
            #
            # Returning None hands the question to the normal pipeline, which
            # has its own degradation path and will tell the user the lookup
            # failed. What must never happen is rendering "There are 0", which
            # would state as fact something we did not learn.
            logger.warning(
                "fast path intent=%s failed (%s) — deferring to the model", intent.name, exc
            )
            return None

        if row is None or row[0] is None:
            return None

        count = int(row[0])
        elapsed_ms = (time.perf_counter() - started) * 1000
        fields = {"n": count}
        for i, value in enumerate(values):
            fields[f"v{i}"] = value
        template = intent.template if count else intent.zero_template
        text = template.format(**fields)

        logger.info(
            "fast path HIT intent=%s values=%r n=%s %.1fms",
            intent.name, values, count, elapsed_ms,
        )
        return FastAnswer(
            text=text,
            intent=intent.name,
            sql=sql,
            params=tuple(values),
            rows=[{"n": count}],
            elapsed_ms=elapsed_ms,
        )

    return None
