# Copyright (c) 2026 Yash Garad. All rights reserved.

"""THE canonical list of tables the assistant may read.

This module is the single source of truth for the backend. Both places that
previously kept their own copy now import from here:

    academics/management/commands/setup_readonly_role.py   (issues the GRANTs)
    sql_agent/schema.py                                    (builds the prompt)

WHY THE SYNC WORKER DOES NOT IMPORT THIS
sync_worker runs in a SEPARATE container with its own build context, so it
cannot import backend code — there is no Python path that reaches this file from
there, and making one would mean either restructuring both build contexts or
shipping a copy, which is the duplication this module exists to remove.

Instead the sync worker asks the DATABASE what it is allowed to read, at
startup, using the grants this list produced (see sync_worker/config.py). That is
strictly stronger than an import: an import can drift from the actual grants,
whereas the worker literally cannot poll a table Postgres has not granted it.
The database is the arbiter, and this list is what configures the database.

WHAT BELONGS HERE
General institutional data ONLY. Per-student tables — students, enrollments,
attendance, exam_results, fee_payments — are deliberately absent, and adding one
here would immediately widen what the language model can read. Django's own
auth_*/django_* tables are excluded too: they are not college data.

WHERE THE NAMES NOW COME FROM
The list itself lives in config/schema_map.json, which maps the logical name
this codebase uses to the physical name in the college's database. This module
still owns the POLICY — what may be read and what each table means — while the
map owns the NAMES. When the real college schema arrives, the map changes and
this file does not.
"""

from common import schema_map

# DERIVED FROM THE SCHEMA MAP — config/schema_map.json is the source.
#
# This was a literal list, kept in step with the map by a test that compared
# them. Two lists that must agree are a drift bug with a delay on it: the test
# catches disagreement only if someone runs it, and the failure mode is either a
# table the model can no longer read (visible) or one it can read that nobody
# allowlisted (not visible). One source with a derived view cannot drift.
#
# Order still comes from the map, and still matters: schema.py renders the
# prompt in this order, so a reordering changes the prompt prefix and
# invalidates the prefix-cache figures in docs/LATENCY.md even when the set is
# identical.
#
# The tables that used to carry a comment here keep it in the map's _doc, and
# the deliberately-EXCLUDED per-student tables are recorded in the map under
# _excluded with a reason each — so the exclusion reads as a decision rather
# than an oversight somebody later "fixes".
#
# Fails closed: a missing, malformed or empty map raises at import rather than
# yielding an empty allowlist. See common/schema_map.py for why that is not
# defensive programming but the direct lesson of ca69849 and 517a71c.
ALLOWED_TABLES = schema_map.physical_tables()

# One-line statement of what each table IS, rendered into the text-to-SQL
# prompt above its column list by sql_agent/schema.py.
#
# WHY THIS EXISTS
# A bare column dump does not tell the model what a table means, and with two
# tables whose names both begin with "faculty" that was measurably not enough.
# Asked "how many faculty in Engineering have competency level Expert", the
# model wrote:
#
#     SELECT COUNT(*) FROM faculty WHERE department = 'Engineering'
#                                    AND competency_level = 'Expert'
#
# against the 7-row staff directory — inventing two columns that exist only on
# faculty_development, and returning an error instead of 102. Naming the tables
# apart in prose, and saying plainly which one holds the survey, is what fixes
# it. Any table without an entry here simply renders without a note.
TABLE_NOTES = {
    "departments": "The college's own academic departments.",
    # THE REDIRECT LIST HERE HAS TO INCLUDE COUNTS, AND IT DID NOT.
    #
    # It used to end "...for scores, competency levels, experience or
    # development needs use faculty_development instead" — a list that omits
    # the single most common question anyone asks about faculty. Asked "How
    # many faculty are in the Computer Science department?" the model read this
    # note, saw that counting was not in the redirect list, and generated
    #
    #     SELECT COUNT(*) FROM faculty WHERE department_id = (
    #         SELECT id FROM departments WHERE name = 'Computer Science')
    #
    # which returns 2, against the survey's 1,916. Both notes were already
    # reaching the prompt — that was checked before anything was changed. The
    # guidance was simply scoped too narrowly to cover the case.
    #
    # Retrieved from audit log entry 801, not reasoned about.
    #
    # PHRASED AS A REDIRECT, NOT A PROHIBITION, AND THAT ORDERING IS MEASURED.
    # A first attempt led with "DO NOT use this table to COUNT faculty". It
    # stopped the wrong answer and produced NO_QUERY instead — the model took
    # the prohibition and concluded the question was unanswerable rather than
    # switching tables. Telling it where to GO beats telling it where not to be.
    # The worked examples in sql_agent/llm_client.py carry most of the weight;
    # this note only has to agree with them.
    "faculty": (
        "The college's STAFF DIRECTORY: a short contact list of named employees "
        "with email, designation and department_id. ONLY A HANDFUL OF ROWS.\n"
        "  Use it ONLY for a NAMED individual's contact details or designation.\n"
        "  For HOW MANY faculty there are — in total, by department, by rank, "
        "or by any other attribute — use faculty_development, which holds the "
        "college's actual faculty population. Counting rows here counts "
        "directory entries rather than people, and the two differ by three "
        "orders of magnitude."
    ),
    "programs": "Degree programs offered by each department.",
    "courses": "Individual courses, with code, title, credits and description.",
    "courses_prerequisites": "Join table: which course requires which other course.",
    "course_offerings": "A course taught in a particular semester and section.",
    "rooms": "Physical rooms, by building and room number.",
    "class_schedule": "Weekly timetable slots for course offerings.",
    "exam_timetable": "Exam date, time and room per course.",
    "fee_structure": (
        "Fee amounts by program, semester and fee type. `amount` is a plain "
        "number and `currency` holds its unit (INR) — always read the currency "
        "column rather than assuming one."
    ),
    "faculty_development": (
        "THE FACULTY DEVELOPMENT SURVEY: about 13,000 anonymised faculty "
        "records, one row per surveyed academic, keyed by faculty_id like "
        "'FAC_00001'. This is the table to use for ANY question about faculty "
        "numbers, counts by department, academic rank, gender, age, years of "
        "experience, digital/AI/data-literacy scores, TRACK knowledge scores, "
        "teaching effectiveness, student feedback, research publications, "
        "training, competency_level ('Basic', 'Intermediate', 'Advanced', "
        "'Expert') or development need (the 'target' column: 'Low Development "
        "Need', 'Moderate Development Need', 'High Development Need'). Its "
        "'department' column is plain text such as 'Engineering' or 'Computer "
        "Science' and needs NO join to the departments table."
    ),
    "faculty_development_profiles": (
        "Generated prose summaries of the faculty_development survey, one per "
        "department, academic rank, university type, competency level, LMS "
        "usage band, and department-and-rank pair. Useful for counting or "
        "listing the summary documents themselves; for the underlying numbers "
        "query faculty_development."
    ),
}


# --- a note on what deliberately is NOT defined here ---------------------------
#
# Two related lists live in sync_worker/config.py and are NOT mirrored here,
# because mirroring them would recreate exactly the cross-container duplication
# this module exists to remove:
#
#   which tables the worker polls
#       Derived at startup from the grants above plus the presence of an
#       `updated_at` column. `courses_prerequisites` is granted (the SQL agent
#       must JOIN through it to answer "what are the prerequisites for X") but
#       is a bare many-to-many join table with no `updated_at` of its own, and
#       the worker's change detection is built entirely on `updated_at`
#       watermarks. The worker names and logs that exclusion explicitly at
#       startup rather than silently skipping it.
#
#   which tables are embedded for semantic search
#       An editorial judgement about which columns contain prose worth
#       vector-searching, not something derivable from grants, so it stays with
#       the code that acts on it.
