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
"""

# Order is meaningful only for prompt readability (schema.py renders in this
# order); the grants and the sync worker are order-independent.
ALLOWED_TABLES = [
    "departments",
    "faculty",
    "programs",
    "courses",
    "courses_prerequisites",
    "course_offerings",
    "rooms",
    "class_schedule",
    "exam_timetable",
    "fee_structure",
    # --- imported faculty development dataset (see academics/models.py) -------
    # Anonymised survey data: 13,000 rows keyed by an opaque "FAC_00001" code
    # with no names, emails or any means of identifying a person. It is
    # institutional analytics, not per-student data, so it belongs here.
    "faculty_development",
    # Prose summaries generated from the table above; this is what the RAG path
    # actually retrieves. Readable by the SQL agent too, so it can answer
    # "how many profile documents are there" style questions coherently.
    "faculty_development_profiles",
]

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
    "faculty": (
        "The college's STAFF DIRECTORY: named individual employees with email, "
        "designation and a department_id. Only a handful of rows. This is NOT "
        "the faculty development survey — for scores, competency levels, "
        "experience or development needs use faculty_development instead."
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
