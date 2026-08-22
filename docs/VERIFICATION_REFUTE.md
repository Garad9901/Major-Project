# Refuting an answer, not just declining to bless it

Copyright (c) 2026 Yash Garad. All rights reserved.

**Date:** 22 August 2026
**Status:** rule 1 **shipped**. Rule 2 **proposed, not implemented** — it needs
the cost analysis in the last section, and a precondition that is not yet met.

---

## The defect this comes from

Audit log entry 801, found by serving production traffic:

```
question       How many faculty are in the Computer Science department?
generated_sql  SELECT COUNT(*) FROM faculty WHERE department_id = (
                   SELECT id FROM departments WHERE name = 'Computer Science')
returns        2                      (it counted an 11-row staff directory)
truth          1,916                  (faculty_development, the 13,000-row survey)
final_answer   "There are 2,014 faculty in the Computer Science department."
verification   timed out; shipped with a hedge
```

Two defects. The wrong table is fixed separately. This document is about the
second: **synthesis was handed `{'count': 2}` and wrote 2,014.**

### What the checker already knew

`fast_check` computed three things and returned two. Reproduced exactly:

```
decided : False
reason  : 1 number(s) not found in source: [2014.0]
source numbers : [2.0]
answer numbers : [2014.0]
```

It had established that the figure was **absent from the source** — positive
evidence of fabrication — and returned `decided=False`, which means *"I cannot
tell, ask the LLM"*. The evidence was discarded at the point it was strongest.
The LLM tier then timed out and the answer shipped hedged.

Confirmed that this was the **ungrounded-number branch** and not the length or
proper-noun guard, so the answer reached that test on its merits rather than
incidentally.

### Why a hedge is not enough for a single figure

For prose, shipping with *"this could not be fact-checked"* is the right trade —
the reader keeps a mostly-useful answer and knows to check it. For an answer
whose entire load-bearing content is **one number**, it is not: a reader takes
the number and drops the hedge. A wrong faculty count or fee reaches someone who
acts on it.

---

## THE BOUNDARY: suppress and say so. Never substitute.

**On refutation, the figure is removed and the user is told. The source value is
never put in its place, and a scalar is never auto-corrected.**

This is a stated boundary, not an implementation detail, and entry 801 is the
argument for it. Had a refute rule fired and "corrected" the answer to the
source value, production would have shipped:

> There are **2** faculty in Computer Science.

marked **CONFIRMED**, because it matches the evidence exactly. That is strictly
worse than 2,014 hedged — the hedge was the only thing making a reader doubt it.

Verification's warrant is precisely *"this number is not supported by the
evidence"*. It is **not** *"this other number is right"*, because it cannot see
that the evidence came from the wrong table. The two claims look similar and are
not: the first is a statement about consistency, which this module can make; the
second is a statement about the world, which it cannot.

It follows that the ordering of the two fixes was **load-bearing, not
incidental**. Fixing the wrong table first is what stopped this fix from
manufacturing a confident wrong answer.

The suppression message therefore contains **no digits at all** — not the
fabricated figure, not the retrieved one. There is a test asserting that.

---

## Rule 1 — contradicted scalar (SHIPPED)

Fires only when nothing is left to interpret:

| Condition | |
|---|---|
| SQL ran without error | a failed lookup is not evidence of anything |
| exactly **one row**, **one column** | no ambiguity about which figure the answer owed |
| that value is **numeric** | `bool` excluded — it is an `int` subclass and not a measurement |
| the answer contains ≥1 number | an answer with no figure cannot contradict one |
| **none** of the answer's numbers match the scalar | see below |

**"None match", not "any differs".** This is what makes derived arithmetic safe.
An answer reading *"1,916, which is about 15% of the college"* contains both
1916 and 15; the scalar is present, so the rule does not fire. Only an answer
that never states the retrieved figure at all is refuted.

**Its entry conditions are its own, not the confirm path's.** A wrong decline
costs seconds of LLM time; a wrong refutation suppresses a correct answer in
front of a user. Raising the consequence raises the bar on the input. Concretely
the refute check runs **before** the confirm path's guards, because every one of
them declines — a contradicted scalar inside a 900-character answer would
otherwise be handed to the LLM tier and never looked at. The one guard it does
not jump is the SQL-error check, which lives inside the refute function itself.

The length cap is deliberately **not** inherited: a fabricated count is just as
wrong inside a long answer, and the comparison is exact either way.

**No fixture cost analysis, because there is nothing ambiguous to cost.** The
rule fires only on a single numeric scalar that the answer never mentions. 15
tests cover it, most asserting it does **not** fire.

---

## Rule 2 — general ungrounded number (PROPOSED, NOT IMPLEMENTED)

The obvious generalisation is *"any number in the answer that is absent from the
source refutes it"*. It is not safe yet, because these all produce legitimately
ungrounded figures:

| Source of a legitimate ungrounded number | Example |
|---|---|
| **Derived arithmetic** | two counts → an average, a ratio, a percentage |
| **Echoed from the question** | "how many of the **8** departments…" |
| **Years and dates** | not present in the rows |
| **Formatting variance** | `2,014` / `2014` / `1916.0` / currency / percent |

### Precondition, which is not met

**The number normaliser must be verified airtight in both directions before
`ungrounded` is allowed to refute anything, and it must be tested directly
rather than through the check that consumes it.**

`_matches_a_source_number` currently carries a rounding tolerance tuned for
*confirming*: it accepts 67.2 for a stored 67.20 while keeping 730 and 731
apart. Under confirmation a normaliser bug costs a spurious LLM call. Under
refutation the same bug suppresses a correct answer. The asymmetry means it
needs its own direct test suite covering at least:

- thousands separators, both directions
- trailing `.0` on integer-valued floats
- currency symbols and percent signs adjacent to digits
- negative numbers and numbers in parentheses
- the 730/731 boundary in both directions
- very large and very small magnitudes where relative tolerance behaves oddly

### Cost analysis still owed

Before rule 2 ships I would run the experiment harness over the fixtures and
report, per answer: numbers in the answer, numbers in the source, which would
be classed ungrounded, and whether the answer is actually correct. The output is
a **false-suppression rate** — correct answers that rule 2 would have removed.

That analysis has not been run. I am not proposing a threshold until it has,
because the number that matters is not "how often does it fire" but "how often
does it fire on an answer that was right".

**Recommendation: ship rule 1 alone, run rule 2 in shadow mode first** — log
what it *would* have suppressed against real traffic for a period, then decide
from that record rather than from the 10-pair fixture set.

---

## Prompt-design note this produced

Recorded here because it will recur every time a table note needs tightening.

The first attempt at the wrong-table fix led with a prohibition:

> DO NOT use this table to COUNT faculty

Measured result: the model stopped producing the wrong query and produced
**`NO_QUERY`** instead — it dropped the capability rather than redirecting it.

> **Prohibition removes; it does not steer. A small model needs somewhere to go,
> not just somewhere to avoid.** Redirect plus a worked example does what a ban
> does not.

The fix that worked was to phrase the note as a redirect ("for how many
faculty… use `faculty_development`") and put the weight on four worked examples
in the SQL system prompt, which previously had none. This is general to 7B-class
models and applies to every future note.
