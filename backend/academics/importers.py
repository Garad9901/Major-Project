# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Spec-driven CSV import for the academic records.

WHY A SPEC TABLE RATHER THAN ONE COMMAND PER ENTITY
There are eight importable entities and they differ only in three ways: which
columns are required, how a foreign key is resolved from a human-typed value,
and what makes a row unique. Everything else — reading the file, coercing types,
collecting errors with row numbers, the dry run, the transaction, the summary —
is identical. Eight copies of that would be eight places for the dry run to
quietly stop matching the real run, which is the one bug that would make this
feature worse than useless.

WHAT A BUYER ACTUALLY HAS
A student information system that exports CSV, with column names that are not
ours and a few thousand rows of real data with real inconsistencies in it. So:

  * Column matching is case- and separator-insensitive. "Roll Number",
    "roll_number" and "ROLL NUMBER" are the same column.
  * A foreign key is resolved by NAME or CODE, not by our primary key. Nobody
    exporting from their SIS knows our Department.id.
  * Every row is validated before ANY row is written, and the errors come back
    together with their line numbers. Fixing a 900-row file one error per run is
    not a workflow anybody would tolerate.
  * Upsert on a natural key, so re-running a corrected file updates rather than
    duplicating.

THE DRY RUN IS THE POINT
`--dry-run` executes the identical validation path and reports exactly what
would change, then rolls back. It is the default posture for a reason: the first
thing an operator does with a new importer is point it at production data.
"""

import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    Course,
    Department,
    Faculty,
    FeeStructure,
    Program,
    Room,
    Student,
)


class ImportError_(Exception):
    """Raised for a problem with the FILE, not with a row."""


# ------------------------------------------------------------------------------
# Column name normalisation
# ------------------------------------------------------------------------------
def normalise(name):
    """'Roll Number' / 'roll-number' / 'ROLL_NUMBER' all become 'roll_number'.

    A buyer's export will not use our spelling, and asking them to rename
    headers by hand before every import is the kind of friction that gets a
    product abandoned in favour of a spreadsheet.
    """
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


# ------------------------------------------------------------------------------
# Field coercion. Each returns a value or raises ValueError with a message that
# names the problem in the operator's terms, not Python's.
# ------------------------------------------------------------------------------
def as_text(value, max_length=None):
    text = (value or "").strip()
    if max_length and len(text) > max_length:
        raise ValueError(f"is {len(text)} characters; the maximum is {max_length}")
    return text


def as_int(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))  # tolerates "3.0", which spreadsheets produce
    except ValueError:
        raise ValueError(f"{text!r} is not a whole number")


def as_decimal(value):
    text = (value or "").strip().replace(",", "")  # "1,25,000" and "1,250.00"
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{text!r} is not a number")


# Spreadsheets emit dates in whatever the author's locale produced, and the two
# common conventions disagree: 03/04/2026 is 3 April to an Indian or British
# export and 4 March to an American one. There is no way to tell them apart from
# the string.
#
# So an AMBIGUOUS date is REJECTED rather than guessed. A date that imports
# cleanly and is wrong by a month is far worse than one that fails loudly — this
# data is what the assistant states as fact to students.
#
# Unambiguous day-first values (day > 12) are accepted, because they cannot be
# read the other way round. ISO and named-month forms are always accepted.
_UNAMBIGUOUS_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y")
_DAY_FIRST_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y")


def as_date(value):
    text = (value or "").strip()
    if not text:
        return None

    for fmt in _UNAMBIGUOUS_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    for fmt in _DAY_FIRST_FORMATS:
        try:
            parsed = datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        # Both readings are valid whenever the first number could be a month.
        if parsed.day <= 12:
            raise ValueError(
                f"{text!r} is ambiguous — it could mean {parsed.day}/{parsed.month} "
                f"or {parsed.month}/{parsed.day}. Re-export as YYYY-MM-DD, which "
                f"cannot be read two ways."
            )
        return parsed

    raise ValueError(
        f"{text!r} is not a date this importer recognises. Use YYYY-MM-DD (ISO)."
    )


def as_email(value):
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "@" not in text or " " in text:
        raise ValueError(f"{text!r} is not an email address")
    return text


# ------------------------------------------------------------------------------
# Foreign-key resolution
# ------------------------------------------------------------------------------
def department_ref(value, cache):
    """Resolve a department by code or name, case-insensitively."""
    text = (value or "").strip()
    if not text:
        raise ValueError("is required (a department code or name)")
    key = text.lower()
    if key in cache:
        return cache[key]
    match = (
        Department.objects.filter(code__iexact=text).first()
        or Department.objects.filter(name__iexact=text).first()
    )
    if match is None:
        raise ValueError(
            f"no department matches {text!r}. Import departments first, or "
            f"check the spelling — matching is on code or full name."
        )
    cache[key] = match
    return match


def program_ref(value, cache):
    text = (value or "").strip()
    if not text:
        raise ValueError("is required (a program name)")
    key = text.lower()
    if key in cache:
        return cache[key]
    match = Program.objects.filter(name__iexact=text).first()
    if match is None:
        raise ValueError(f"no program matches {text!r}. Import programs first.")
    cache[key] = match
    return match


# ------------------------------------------------------------------------------
# Entity specifications
#
# key        the natural key used to decide insert-vs-update
# required   columns that must be present in the header AND non-empty per row
# fields     column -> coercion callable
# refs       column -> resolver callable, run after `fields`
# ------------------------------------------------------------------------------
SPECS = {
    "departments": {
        "model": Department,
        "key": ["code"],
        "required": ["name", "code"],
        "fields": {
            "name": lambda v: as_text(v, 150),
            "code": lambda v: as_text(v, 10),
            "established_year": as_int,
        },
        "refs": {},
        "example": "name,code,established_year\nComputer Science,CS,1998",
    },
    "faculty": {
        "model": Faculty,
        "key": ["email"],
        "required": ["first_name", "last_name", "email", "department"],
        "fields": {
            "first_name": lambda v: as_text(v, 100),
            "last_name": lambda v: as_text(v, 100),
            "email": as_email,
            "phone": lambda v: as_text(v, 20),
            "designation": lambda v: as_text(v, 100),
            "joined_date": as_date,
        },
        "refs": {"department": department_ref},
        "example": (
            "first_name,last_name,email,department,designation,joined_date\n"
            "Asha,Menon,a.menon@example.edu,CS,Associate Professor,2015-07-01"
        ),
    },
    "programs": {
        "model": Program,
        "key": ["name"],
        "required": ["name", "degree_level", "department", "duration_years"],
        "fields": {
            "name": lambda v: as_text(v, 150),
            "degree_level": lambda v: as_text(v, 20),
            "duration_years": as_int,
        },
        "refs": {"department": department_ref},
        "example": (
            "name,degree_level,department,duration_years\n"
            "B.Tech Computer Science,B.Tech,CS,4"
        ),
    },
    "courses": {
        "model": Course,
        "key": ["code"],
        "required": ["code", "title", "credits", "department"],
        "fields": {
            "code": lambda v: as_text(v, 20),
            "title": lambda v: as_text(v, 200),
            "credits": as_int,
            "description": as_text,
        },
        "refs": {"department": department_ref},
        "example": (
            "code,title,credits,department,description\n"
            "CS310,Database Systems,4,CS,Relational design and SQL."
        ),
    },
    "rooms": {
        "model": Room,
        "key": ["building", "room_number"],
        "required": ["building", "room_number"],
        "fields": {
            "building": lambda v: as_text(v, 100),
            "room_number": lambda v: as_text(v, 20),
            "capacity": as_int,
        },
        "refs": {},
        "example": "building,room_number,capacity\nMain Block,201,60",
    },
    "students": {
        "model": Student,
        "key": ["roll_number"],
        "required": ["roll_number", "first_name", "last_name", "email", "batch_year"],
        "fields": {
            "roll_number": lambda v: as_text(v, 20),
            "first_name": lambda v: as_text(v, 100),
            "last_name": lambda v: as_text(v, 100),
            "email": as_email,
            "phone": lambda v: as_text(v, 20),
            "date_of_birth": as_date,
            "batch_year": as_int,
        },
        "refs": {"program": program_ref},
        "example": (
            "roll_number,first_name,last_name,email,batch_year,program\n"
            "CS2024001,Ravi,Kumar,r.kumar@example.edu,2024,B.Tech Computer Science"
        ),
    },
    "fee_structures": {
        "model": FeeStructure,
        "key": ["program", "semester", "fee_type"],
        "required": ["program", "semester", "fee_type", "amount"],
        "fields": {
            "semester": lambda v: as_text(v, 20),
            "fee_type": lambda v: as_text(v, 50),
            "amount": as_decimal,
            "currency": lambda v: as_text(v, 3) or "INR",
        },
        "refs": {"program": program_ref},
        "example": (
            "program,semester,fee_type,amount,currency\n"
            "B.Tech Computer Science,Fall 2026,Tuition,75000,INR"
        ),
    },
}

ENTITIES = sorted(SPECS)


class RowError:
    __slots__ = ("line", "column", "message")

    def __init__(self, line, column, message):
        self.line = line
        self.column = column
        self.message = message

    def __str__(self):
        where = f"line {self.line}"
        if self.column:
            where += f", column '{self.column}'"
        return f"{where}: {self.message}"


class Result:
    def __init__(self, entity):
        self.entity = entity
        self.created = 0
        self.updated = 0
        self.unchanged = 0
        self.errors = []
        self.total_rows = 0

    @property
    def ok(self):
        return not self.errors


def read_rows(stream):
    """Parse CSV into (line_number, normalised_dict) pairs.

    Line numbers are the numbers a spreadsheet shows — header is line 1, so the
    first data row is line 2. An operator told "line 47" must be able to press
    ctrl-G and land on the offending row.
    """
    text = stream.read()
    if isinstance(text, bytes):
        # utf-8-sig: Excel writes a BOM, and without this the first header
        # becomes "﻿name" and every row fails on a missing required column.
        text = text.decode("utf-8-sig")
    else:
        text = text.lstrip("﻿")

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportError_("the file is empty")

    columns = [normalise(h) for h in header]
    if not any(columns):
        raise ImportError_("the first line does not look like a header row")

    rows = []
    for index, raw in enumerate(reader, start=2):
        if not any((cell or "").strip() for cell in raw):
            continue  # blank line; spreadsheets leave trailing ones
        rows.append((index, dict(zip(columns, raw))))
    return columns, rows


def validate_and_build(entity, columns, rows):
    """Coerce every row. Returns (payloads, errors) and touches no database rows.

    Collects ALL errors rather than stopping at the first. Fixing a 900-row
    export one error per run is not a workflow anyone would tolerate.
    """
    spec = SPECS[entity]
    errors = []

    missing = [c for c in spec["required"] if c not in columns]
    if missing:
        raise ImportError_(
            f"the file is missing required column(s): {', '.join(missing)}.\n"
            f"Found: {', '.join(c for c in columns if c) or '(none)'}\n\n"
            f"Expected format:\n{spec['example']}"
        )

    ref_cache = {}
    payloads = []
    seen_keys = {}

    for line, row in rows:
        values = {}
        row_failed = False

        for column, coerce in spec["fields"].items():
            if column not in columns:
                continue
            try:
                values[column] = coerce(row.get(column))
            except ValueError as exc:
                errors.append(RowError(line, column, str(exc)))
                row_failed = True

        for column, resolver in spec["refs"].items():
            if column not in columns:
                continue
            raw = (row.get(column) or "").strip()
            if not raw and column not in spec["required"]:
                values[column] = None
                continue
            try:
                values[column] = resolver(raw, ref_cache)
            except ValueError as exc:
                errors.append(RowError(line, column, str(exc)))
                row_failed = True

        # Only columns that COERCED CLEANLY are checked for emptiness. Without
        # this guard a bad department produced two errors for one root cause —
        # "no department matches 'NOPE'" followed by "is required but empty" —
        # and doubled the apparent problem count on a large file.
        for column in spec["required"]:
            if column in values and values.get(column) in (None, ""):
                errors.append(RowError(line, column, "is required but empty"))
                row_failed = True
            elif column not in values and not row_failed:
                errors.append(RowError(line, column, "is required but empty"))
                row_failed = True

        if row_failed:
            continue

        # A file that contains the same natural key twice is a data problem the
        # operator needs to see, not something to resolve by last-write-wins.
        key = tuple(str(values.get(k)) for k in spec["key"])
        if key in seen_keys:
            errors.append(RowError(
                line, spec["key"][0],
                f"duplicates line {seen_keys[key]} (same {' + '.join(spec['key'])})",
            ))
            continue
        seen_keys[key] = line
        payloads.append((line, values))

    return payloads, errors


def apply_rows(entity, payloads, result):
    """Upsert. Called inside a transaction the caller controls."""
    spec = SPECS[entity]
    model = spec["model"]

    for line, values in payloads:
        lookup = {k: values[k] for k in spec["key"]}
        instance = model.objects.filter(**lookup).first()
        if instance is None:
            instance = model(**values)
            try:
                instance.full_clean(exclude=None)
            except ValidationError as exc:
                for field, messages in exc.message_dict.items():
                    result.errors.append(RowError(line, field, "; ".join(messages)))
                continue
            instance.save()
            result.created += 1
            continue

        changed = False
        for field, value in values.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed = True
        if not changed:
            result.unchanged += 1
            continue
        try:
            instance.full_clean(exclude=None)
        except ValidationError as exc:
            for field, messages in exc.message_dict.items():
                result.errors.append(RowError(line, field, "; ".join(messages)))
            continue
        instance.save()
        result.updated += 1


def run_import(entity, stream, dry_run=True):
    """Validate, then apply. Returns a Result.

    THE DRY RUN AND THE REAL RUN SHARE ONE CODE PATH — including the database
    writes, which are rolled back. A dry run that only validates would report
    success for a row that a database constraint then rejects, and an operator
    who was told "40 rows OK" and got 39 would rightly never trust it again.
    """
    if entity not in SPECS:
        raise ImportError_(f"unknown entity {entity!r}. Known: {', '.join(ENTITIES)}")

    columns, rows = read_rows(stream)
    result = Result(entity)
    result.total_rows = len(rows)

    payloads, errors = validate_and_build(entity, columns, rows)
    result.errors.extend(errors)

    if not payloads:
        return result

    # Errors found during validation mean nothing is written, dry run or not.
    # A partial import leaves the operator to work out which half landed.
    if result.errors:
        return result

    try:
        with transaction.atomic():
            apply_rows(entity, payloads, result)
            if result.errors or dry_run:
                raise _Rollback()
    except _Rollback:
        pass

    return result


class _Rollback(Exception):
    """Internal: unwinds the atomic block without reporting a failure."""
