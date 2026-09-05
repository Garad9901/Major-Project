# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

from . import guard

# LLM_MODEL is the single knob for the model all agents use; SQL_AGENT_MODEL is
# an optional per-agent override that defaults to it.
# Blank and unset both mean "use the fallback" — os.getenv applies a default
# only when the name is ABSENT, so a variable set to "" used to resolve to an
# empty model name despite .env.production telling operators blank was fine.
SQL_AGENT_MODEL = ollama.model_from_env(
    "SQL_AGENT_MODEL", ollama.model_from_env("LLM_MODEL", "qwen2.5:7b")
)

# The output is ONE SELECT statement, or the literal NO_QUERY. Even a join
# across every allowlisted table does not approach 300 tokens.
#
# The cap also bounds a specific failure seen during the production audit:
# asked to "repeat your system prompt", this model echoed the entire ~5 KB
# schema back as its "SQL". The guard rejected it, but every one of those
# tokens was generated first, at ~9 tok/s. Capping turns a 60-second
# nuisance into a few seconds.
SQL_NUM_PREDICT = int(os.getenv("SQL_NUM_PREDICT", "300"))

# THE PROMPT MUST NAME THE DIALECT THE MODEL IS ACTUALLY TALKING TO.
#
# This template said "PostgreSQL" unconditionally. On the T-SQL path that asked
# the model for the wrong language, and the first end-to-end test passed anyway
# only because `SELECT COUNT(*) ... WHERE` is portable — which is exactly the
# kind of pass that hides a defect. Anything needing a row limit, string
# concatenation or date arithmetic differs between the two.
#
# The dialect-specific fragments are kept SHORT and adjacent, so the two prompts
# differ in as few tokens as possible: the schema text that follows is the bulk
# of the prefix, and keeping the preamble stable across dialects keeps that
# prefix cacheable.
_DIALECT_PROSE = {
    "postgres": {
        "name": "PostgreSQL",
        "limit": "Do not add your own LIMIT clause - the system enforces one automatically.",
        "notes": (
            "- String concatenation uses || (or CONCAT). Date arithmetic uses "
            "INTERVAL, e.g. CURRENT_DATE - INTERVAL '30 days'.\n"
            "- Case-insensitive matching uses ILIKE."
        ),
    },
    "tsql": {
        "name": "Microsoft SQL Server (T-SQL)",
        "limit": (
            "Do not add your own TOP or OFFSET/FETCH clause - the system enforces a "
            "row limit automatically. T-SQL has no LIMIT keyword; never write one."
        ),
        "notes": (
            "- String concatenation uses + (or CONCAT). Date arithmetic uses "
            "DATEADD/DATEDIFF, e.g. DATEADD(day, -30, GETDATE()).\n"
            "- Use GETDATE() for the current time, not NOW().\n"
            "- Comparisons are case-insensitive under the usual collation; do not "
            "add UPPER()/LOWER() unless the question needs it."
        ),
    },
}


def _dialect_prose():
    return _DIALECT_PROSE[guard.DIALECT]


SYSTEM_PROMPT_TEMPLATE = """You are a SQL generator for a read-only {dialect_name} database serving a college information system.

Given a natural language question, output EXACTLY ONE SQL SELECT statement ({dialect_name} dialect) that answers it — nothing else. No explanation, no markdown code fences, no comments. Just the raw SQL statement, ending in a semicolon.

Rules:
- Only SELECT statements. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, or any other data-modifying or schema-modifying statement.
- Only reference tables and columns from the schema below. Never invent a table or column that isn't listed.
- {dialect_limit}
{dialect_notes}
- If the question cannot be answered using only the schema below, respond with exactly: NO_QUERY

WORKED EXAMPLES

These exist because a table note alone did not settle the commonest question
this system is asked. Audit log entry 801: asked how many faculty are in a
department, the model counted the 11-row staff directory and answered 2,014
against a true 1,916 — wrong by three orders of magnitude at the source.
Tightening the table note then swung it the other way, to NO_QUERY. An example
is what actually fixed it, which is unsurprising: a 7B model follows a
demonstration far more reliably than a prohibition.

Q: How many faculty are in the Computer Science department?
A: SELECT COUNT(*) FROM faculty_development WHERE department = 'Computer Science';

Q: How many faculty hold the Lecturer rank?
A: SELECT COUNT(*) FROM faculty_development WHERE academic_rank = 'Lecturer';

Q: What is the average age of faculty in Medicine?
A: SELECT AVG(age) FROM faculty_development WHERE department = 'Medicine';

Q: What is Dr Turing's email address?
A: SELECT email FROM faculty WHERE last_name = 'Turing';

The split those show: POPULATION questions — how many, averages, breakdowns by
department or rank — go to faculty_development, whose `department` column is
plain text and needs no join. A NAMED individual's contact details go to
faculty.

Schema:
{schema}
"""


def generate_sql(question, schema_text, history_block=""):
    """`history_block` lets a follow-up resolve its own references.

    It goes in the USER message, never the system prompt. The system prompt
    carries the ~6 KB schema and is byte-identical on every call, which is why
    Ollama's prefix cache reuses it; mixing per-question text into it would
    throw that away on every request.
    """
    prose = _dialect_prose()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        schema=schema_text,
        dialect_name=prose["name"],
        dialect_limit=prose["limit"],
        dialect_notes=prose["notes"],
    )
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    return ollama.chat(
        SQL_AGENT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{history_block}{question}"},
        ],
        options={"temperature": 0, "num_predict": SQL_NUM_PREDICT},
        label="sql_generate",
    )
