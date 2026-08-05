# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Load the faculty development CSV into Postgres, then rebuild the prose
profile documents that give the RAG path something to retrieve.

IDEMPOTENT BY CONSTRUCTION
Both writes are upserts keyed on natural keys, never blind inserts:

    faculty_development           upsert on faculty_id  (the CSV's own ID)
    faculty_development_profiles  upsert on (scope, scope_key)

So re-running this command against the same file produces the same row counts,
not duplicates. Re-running it against an updated file updates in place and adds
only genuinely new IDs. Nothing is deleted implicitly — see --prune.

See RUNBOOK.md ("Loading the faculty development dataset") for operator steps.
"""

import csv
import os
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academics.models import FacultyDevelopment, FacultyDevelopmentProfile

# The exact header this loader was written against. Validated rather than
# assumed: if the source file ever changes shape, this command must fail loudly
# instead of silently loading a subset or writing nulls into typed columns.
#
# Every one of these maps to its model field by a plain .lower() — including the
# awkward ones (Faculty_ID -> faculty_id, TRACK_* -> track_*, LMS_* -> lms_*,
# AI_Tool_Adoption_Score -> ai_tool_adoption_score). The mapping is asserted in
# _field_for() rather than trusted.
EXPECTED_COLUMNS = [
    "Faculty_ID", "Age", "Gender", "Academic_Rank",
    "Teaching_Experience_Years", "Research_Experience_Years",
    "Department", "University_Type",
    "Institution_Digital_Infrastructure", "Institutional_Support_Score",
    "Big_Data_Readiness_Score", "LMS_Usage_Frequency",
    "Online_Teaching_Hours_Per_Week", "Digital_Tool_Usage_Score",
    "Data_Literacy_Score", "AI_Tool_Adoption_Score",
    "TRACK_Technology_Knowledge", "TRACK_Research_Analytics_Knowledge",
    "TRACK_Academic_Content_Knowledge", "TRACK_Collaborative_Knowledge",
    "TRACK_Knowledge_Integration",
    "Student_Feedback_Score", "Teaching_Effectiveness_Score",
    "Research_Publications", "Research_Productivity_Score",
    "Publication_Quality_Index",
    "Training_Programs_Attended", "Professional_Development_Score",
    "Collaboration_Index", "Innovation_in_Teaching_Score",
    "Administrative_Participation_Score",
    "Overall_Faculty_Development_Index", "Competency_Level", "Target",
]

_MODEL_FIELDS = {f.name for f in FacultyDevelopment._meta.get_fields()}


def _field_for(column):
    """CSV header -> model field name, verified against the model."""
    name = column.lower()
    if name not in _MODEL_FIELDS:
        raise CommandError(
            f"CSV column {column!r} maps to {name!r}, which is not a field on "
            "FacultyDevelopment. The source file and the model have diverged."
        )
    return name


# Built once: field name -> the converter its column needs.
def _build_converters():
    converters = {}
    for column in EXPECTED_COLUMNS:
        name = _field_for(column)
        internal = FacultyDevelopment._meta.get_field(name).get_internal_type()
        if internal == "DecimalField":
            converters[name] = Decimal
        elif internal in ("PositiveSmallIntegerField", "PositiveIntegerField", "IntegerField"):
            converters[name] = int
        else:
            converters[name] = str
    return converters


CONVERTERS = _build_converters()

# --- score groups used by the prose templates ------------------------------
_DIGITAL = [
    "big_data_readiness_score", "data_literacy_score",
    "ai_tool_adoption_score", "digital_tool_usage_score",
]
_TEACHING = [
    "student_feedback_score", "teaching_effectiveness_score",
    "innovation_in_teaching_score",
]
_RESEARCH = [
    "research_publications", "research_productivity_score",
    "publication_quality_index",
]
_DEVELOPMENT = [
    "training_programs_attended", "professional_development_score",
    "collaboration_index", "administrative_participation_score",
]
_CONTEXT = [
    "institution_digital_infrastructure", "institutional_support_score",
    "online_teaching_hours_per_week",
]
_ALL_NUMERIC = sorted(set(
    _DIGITAL + _TEACHING + _RESEARCH + _DEVELOPMENT + _CONTEXT
    + ["overall_faculty_development_index"]
))
_CATEGORICAL = ["competency_level", "target", "lms_usage_frequency"]


class Command(BaseCommand):
    help = (
        "Load the faculty development dataset CSV into Postgres and rebuild the "
        "prose profile documents used by the RAG path. Idempotent: safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=os.getenv("FACULTY_DATASET_CSV", "/tmp/faculty_development.csv"),
            help=(
                "Path to the CSV INSIDE THE CONTAINER. Copy it in first with "
                "`docker compose cp <host-path> backend:/tmp/faculty_development.csv`. "
                "Defaults to /tmp/faculty_development.csv, or $FACULTY_DATASET_CSV."
            ),
        )
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and validate the CSV, report what would change, write nothing.",
        )
        parser.add_argument(
            "--profiles-only", action="store_true",
            help="Skip the CSV entirely; rebuild profile documents from rows already loaded.",
        )
        parser.add_argument(
            "--prune", action="store_true",
            help=(
                "Also DELETE faculty_development rows whose faculty_id is absent "
                "from the CSV. Off by default so a truncated file cannot silently "
                "destroy data."
            ),
        )

    def handle(self, *args, **options):
        if options["profiles_only"]:
            if not FacultyDevelopment.objects.exists():
                raise CommandError("--profiles-only given but faculty_development is empty.")
            self._rebuild_profiles(dry_run=options["dry_run"])
            return

        rows = self._read_csv(options["csv"])
        self._load_rows(rows, options)
        if not options["dry_run"]:
            self._rebuild_profiles(dry_run=False)

    # -- CSV ----------------------------------------------------------------

    def _read_csv(self, path):
        if not os.path.exists(path):
            raise CommandError(
                f"CSV not found at {path}.\n"
                "The file lives on the HOST; the backend runs in a container. Copy it in:\n"
                "  docker compose cp \"<host path>\" backend:/tmp/faculty_development.csv"
            )

        # utf-8-sig: the file may carry a BOM, which would otherwise corrupt the
        # first header name and make the header check fail confusingly.
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            header = reader.fieldnames or []
            if header != EXPECTED_COLUMNS:
                missing = [c for c in EXPECTED_COLUMNS if c not in header]
                extra = [c for c in header if c not in EXPECTED_COLUMNS]
                raise CommandError(
                    "CSV header does not match what this loader expects.\n"
                    f"  missing: {missing or 'none'}\n"
                    f"  unexpected: {extra or 'none'}\n"
                    "Update EXPECTED_COLUMNS and the model together if the source changed."
                )
            raw_rows = list(reader)

        if not raw_rows:
            raise CommandError(f"{path} has a valid header but no data rows.")

        records = []
        for line_no, raw in enumerate(raw_rows, start=2):  # line 1 is the header
            record = {}
            for column in EXPECTED_COLUMNS:
                value = (raw[column] or "").strip()
                name = _field_for(column)
                if value == "":
                    raise CommandError(
                        f"line {line_no}: column {column!r} is empty. This dataset "
                        "is expected to have no missing values; refusing to guess."
                    )
                try:
                    record[name] = CONVERTERS[name](value)
                except (ValueError, InvalidOperation) as exc:
                    raise CommandError(
                        f"line {line_no}: column {column!r} value {value!r} is not "
                        f"valid for field {name!r}: {exc}"
                    ) from None
            records.append(record)

        ids = [r["faculty_id"] for r in records]
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        if duplicates:
            raise CommandError(
                f"CSV contains {len(duplicates)} duplicated Faculty_ID value(s), "
                f"e.g. {duplicates[:5]}. The primary key cannot be built from it."
            )

        self.stdout.write(f"Parsed {len(records):,} rows from {path}")
        return records

    def _load_rows(self, records, options):
        incoming = {r["faculty_id"] for r in records}
        existing = set(
            FacultyDevelopment.objects.filter(faculty_id__in=incoming)
            .values_list("faculty_id", flat=True)
        )
        new_count = len(incoming - existing)
        stale = set(FacultyDevelopment.objects.values_list("faculty_id", flat=True)) - incoming

        self.stdout.write(
            f"  {new_count:,} new, {len(existing):,} existing (will be updated in place), "
            f"{len(stale):,} in the database but absent from this CSV"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — nothing written. Re-run without --dry-run to apply."
            ))
            return

        update_fields = [
            _field_for(c) for c in EXPECTED_COLUMNS if _field_for(c) != "faculty_id"
        ] + ["loaded_at"]

        objs = [FacultyDevelopment(**r) for r in records]
        with transaction.atomic():
            FacultyDevelopment.objects.bulk_create(
                objs,
                batch_size=options["batch_size"],
                # ON CONFLICT (faculty_id) DO UPDATE — this is what makes a
                # re-run an update rather than an IntegrityError or a duplicate.
                update_conflicts=True,
                update_fields=update_fields,
                unique_fields=["faculty_id"],
            )
            if options["prune"] and stale:
                FacultyDevelopment.objects.filter(faculty_id__in=stale).delete()
                self.stdout.write(self.style.WARNING(f"  pruned {len(stale):,} stale row(s)"))

        total = FacultyDevelopment.objects.count()
        self.stdout.write(self.style.SUCCESS(f"faculty_development now holds {total:,} rows."))

    # -- synthetic prose profiles -------------------------------------------

    def _rebuild_profiles(self, dry_run):
        """Render real aggregates into readable paragraphs.

        The FIGURES are genuine SQL/Python aggregates over the loaded rows.
        The SENTENCES are a fixed template written here — no model generates
        them, and no such prose exists in the source dataset. See the docstring
        on FacultyDevelopmentProfile for why this exists and what it is not.
        """
        fields = _ALL_NUMERIC + _CATEGORICAL + ["department", "academic_rank", "university_type"]
        rows = list(FacultyDevelopment.objects.values(*fields))
        total = len(rows)

        specs = [
            ("department", "department", lambda r: r["department"]),
            ("academic_rank", "academic rank", lambda r: r["academic_rank"]),
            ("university_type", "university type", lambda r: r["university_type"]),
            ("competency_level", "competency level", lambda r: r["competency_level"]),
            ("lms_usage", "LMS usage frequency", lambda r: r["lms_usage_frequency"]),
        ]

        documents = []
        for scope, label, key_fn in specs:
            groups = defaultdict(list)
            for r in rows:
                groups[key_fn(r)].append(r)
            for key, members in sorted(groups.items()):
                documents.append(self._render_group(scope, label, key, members, total))

        # Crossed scope: department x academic rank. Shorter body, because 32
        # long near-identical documents would crowd out the broader ones in
        # top-k retrieval.
        crossed = defaultdict(list)
        for r in rows:
            crossed[(r["department"], r["academic_rank"])].append(r)
        for (dept, rank), members in sorted(crossed.items()):
            documents.append(self._render_crossed(dept, rank, members))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN — would write {len(documents)} profile document(s)."
            ))
            return

        created = updated = unchanged = 0
        with transaction.atomic():
            for doc in documents:
                obj = FacultyDevelopmentProfile.objects.filter(
                    scope=doc["scope"], scope_key=doc["scope_key"]
                ).first()
                if obj is None:
                    FacultyDevelopmentProfile.objects.create(**doc)
                    created += 1
                elif obj.body != doc["body"] or obj.title != doc["title"]:
                    # Only touch rows whose text actually changed. updated_at is
                    # auto_now, and the sync worker re-embeds anything whose
                    # watermark moves — so writing unconditionally would re-embed
                    # every document on every run for no reason.
                    for k, v in doc.items():
                        setattr(obj, k, v)
                    obj.save()
                    updated += 1
                else:
                    unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f"faculty_development_profiles: {created} created, {updated} updated, "
            f"{unchanged} unchanged ({FacultyDevelopmentProfile.objects.count()} total)."
        ))
        if created or updated:
            self.stdout.write(
                "The sync worker will embed the changed documents into Qdrant "
                "within one poll cycle (default 30s)."
            )

    # -- prose templates ----------------------------------------------------
    #
    # Deliberately plain f-strings. Every number below is computed from the
    # loaded rows; every word between them is fixed text written by hand.

    @staticmethod
    def _avg(members, field):
        return sum(float(m[field]) for m in members) / len(members)

    @staticmethod
    def _modal(members, field):
        counts = Counter(m[field] for m in members)
        value, n = counts.most_common(1)[0]
        return value, n, 100.0 * n / len(members)

    def _render_group(self, scope, label, key, members, total):
        n = len(members)
        avg = {f: self._avg(members, f) for f in _ALL_NUMERIC}
        comp, comp_n, comp_pct = self._modal(members, "competency_level")
        targ, targ_n, targ_pct = self._modal(members, "target")
        lms, _, lms_pct = self._modal(members, "lms_usage_frequency")

        title = f"Faculty development profile by {label}: {key}"
        body = (
            f"This is a summary of faculty development survey data for the {label} "
            f"\"{key}\". It covers {n:,} of the {total:,} faculty records in the "
            f"dataset ({100.0 * n / total:.1f}% of all records). The overall faculty "
            f"development index for this group averages "
            f"{avg['overall_faculty_development_index']:.1f} out of 100.\n\n"

            f"Digital capability and data skills: big data readiness averages "
            f"{avg['big_data_readiness_score']:.1f}, data literacy "
            f"{avg['data_literacy_score']:.1f}, AI tool adoption "
            f"{avg['ai_tool_adoption_score']:.1f}, and general digital tool usage "
            f"{avg['digital_tool_usage_score']:.1f}. The surrounding institutions "
            f"score {avg['institution_digital_infrastructure']:.1f} for digital "
            f"infrastructure and {avg['institutional_support_score']:.1f} for "
            f"institutional support. Learning management system usage in this group "
            f"is most often \"{lms}\" ({lms_pct:.0f}% of the group), and faculty "
            f"spend an average of {avg['online_teaching_hours_per_week']:.1f} hours "
            f"per week teaching online.\n\n"

            f"Teaching quality: student feedback averages "
            f"{avg['student_feedback_score']:.1f} and teaching effectiveness "
            f"{avg['teaching_effectiveness_score']:.1f}, with innovation in teaching "
            f"at {avg['innovation_in_teaching_score']:.1f}.\n\n"

            f"Research output: faculty in this group average "
            f"{avg['research_publications']:.1f} publications each, with a research "
            f"productivity score of {avg['research_productivity_score']:.1f} and a "
            f"publication quality index of {avg['publication_quality_index']:.1f}.\n\n"

            f"Professional development: they have attended "
            f"{avg['training_programs_attended']:.1f} training programmes on average, "
            f"scoring {avg['professional_development_score']:.1f} for professional "
            f"development, {avg['collaboration_index']:.1f} for collaboration, and "
            f"{avg['administrative_participation_score']:.1f} for administrative "
            f"participation.\n\n"

            f"Assessed competency and need: the most common competency level in this "
            f"group is \"{comp}\" ({comp_n:,} faculty, {comp_pct:.0f}%), and the most "
            f"common assessed development need is \"{targ}\" ({targ_n:,} faculty, "
            f"{targ_pct:.0f}%)."
        )
        return {
            "scope": scope, "scope_key": str(key), "title": title,
            "body": body, "faculty_count": n,
        }

    def _render_crossed(self, dept, rank, members):
        n = len(members)
        avg = {f: self._avg(members, f) for f in _ALL_NUMERIC}
        comp, _, _ = self._modal(members, "competency_level")
        targ, _, targ_pct = self._modal(members, "target")

        title = f"Faculty development profile: {rank}s in {dept}"
        body = (
            f"This is a summary of faculty development survey data for staff holding "
            f"the rank of {rank} within the {dept} department, covering {n:,} faculty "
            f"records. Their overall faculty development index averages "
            f"{avg['overall_faculty_development_index']:.1f} out of 100. "
            f"On digital capability they average {avg['big_data_readiness_score']:.1f} "
            f"for big data readiness, {avg['data_literacy_score']:.1f} for data "
            f"literacy, and {avg['ai_tool_adoption_score']:.1f} for AI tool adoption. "
            f"Teaching effectiveness averages "
            f"{avg['teaching_effectiveness_score']:.1f} with student feedback at "
            f"{avg['student_feedback_score']:.1f}. They average "
            f"{avg['research_publications']:.1f} research publications each. The most "
            f"common competency level for this group is \"{comp}\", and the most "
            f"common assessed development need is \"{targ}\" ({targ_pct:.0f}% of the group)."
        )
        return {
            "scope": "department_rank", "scope_key": f"{dept} / {rank}",
            "title": title, "body": body, "faculty_count": n,
        }
