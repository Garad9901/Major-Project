# Copyright (c) 2026 Yash Garad. All rights reserved.

from datetime import date, time
from decimal import Decimal

from common.devonly import DevelopmentOnlyCommand
from django.db import transaction

from academics.models import (
    Attendance,
    ClassSchedule,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    ExamResult,
    ExamTimetable,
    Faculty,
    FeePayment,
    FeeStructure,
    Program,
    Room,
    Student,
)

# ---------------------------------------------------------------------------
# A small but internally CONSISTENT demo dataset. The earlier ad-hoc rows had
# every course pinned to Computer Science and left faculty/programs/fees/
# schedules empty, which made department questions wrong and left SQL-routed
# questions with nothing to return. This replaces all of that.
#
# Idempotent: wipes the academics tables and rebuilds from scratch, so it can
# be re-run any time to get back to a known-good state.
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    # THESE ARE THE EIGHT DEPARTMENTS THE FACULTY DEVELOPMENT SURVEY USES, and
    # that is the whole point of the list.
    #
    # It used to be Computer Science / Mathematics / Chemistry / English /
    # Commerce, which overlapped with the survey on Computer Science ALONE. An
    # evaluator who loaded both then got a system that answered "how many
    # departments are there?" with 5 while every faculty count came from a
    # different set of 8 — the assistant appearing to contradict itself, which
    # is the single worst impression this software can make.
    #
    # The subject content below did not disappear; it was re-homed. Mathematics
    # and Chemistry sit under Science, English under Arts and Humanities, and
    # Commerce under Management, which is where a real institution would put
    # them anyway.
    {"name": "Computer Science", "code": "CS", "established_year": 1986},
    {"name": "Science", "code": "SCI", "established_year": 1965},
    {"name": "Arts and Humanities", "code": "AH", "established_year": 1960},
    {"name": "Management", "code": "MGT", "established_year": 1972},
    {"name": "Engineering", "code": "ENGR", "established_year": 1958},
    {"name": "Education", "code": "EDU", "established_year": 1974},
    {"name": "Social Science", "code": "SOC", "established_year": 1968},
    {"name": "Medicine", "code": "MED", "established_year": 1981},
]

FACULTY = [
    {"first": "Alan", "last": "Turing", "dept": "CS", "designation": "Professor"},
    {"first": "Grace", "last": "Hopper", "dept": "CS", "designation": "Associate Professor"},
    {"first": "Emmy", "last": "Noether", "dept": "SCI", "designation": "Professor"},
    {"first": "Srinivasa", "last": "Ramanujan", "dept": "SCI", "designation": "Assistant Professor"},
    {"first": "Marie", "last": "Curie", "dept": "SCI", "designation": "Professor"},
    {"first": "Virginia", "last": "Woolf", "dept": "AH", "designation": "Associate Professor"},
    {"first": "Adam", "last": "Smith", "dept": "MGT", "designation": "Professor"},
    {"first": "Ada", "last": "Lovelace", "dept": "ENGR", "designation": "Professor"},
    {"first": "Maria", "last": "Montessori", "dept": "EDU", "designation": "Associate Professor"},
    {"first": "Emile", "last": "Durkheim", "dept": "SOC", "designation": "Professor"},
    {"first": "Elizabeth", "last": "Blackwell", "dept": "MED", "designation": "Professor"},
]

PROGRAMS = [
    {"name": "B.Tech Computer Science", "degree_level": "bachelor", "dept": "CS", "duration_years": 4},
    {"name": "M.Tech Computer Science", "degree_level": "master", "dept": "CS", "duration_years": 2},
    {"name": "B.Sc Mathematics", "degree_level": "bachelor", "dept": "SCI", "duration_years": 3},
    {"name": "B.Sc Chemistry", "degree_level": "bachelor", "dept": "SCI", "duration_years": 3},
    {"name": "B.A English", "degree_level": "bachelor", "dept": "AH", "duration_years": 3},
    {"name": "B.Com", "degree_level": "bachelor", "dept": "MGT", "duration_years": 3},
    {"name": "B.Tech Civil Engineering", "degree_level": "bachelor", "dept": "ENGR", "duration_years": 4},
    {"name": "B.Ed", "degree_level": "bachelor", "dept": "EDU", "duration_years": 2},
    {"name": "B.A Sociology", "degree_level": "bachelor", "dept": "SOC", "duration_years": 3},
    {"name": "MBBS", "degree_level": "bachelor", "dept": "MED", "duration_years": 5},
]

COURSES = [
    {"code": "CS501", "title": "Machine Learning Fundamentals", "credits": 4, "dept": "CS",
     "description": "Covers supervised and unsupervised learning, neural networks, and model evaluation."},
    {"code": "CS310", "title": "Database Systems", "credits": 3, "dept": "CS",
     "description": "Relational algebra, SQL, normalization, transactions, and indexing."},
    {"code": "CS420", "title": "Operating Systems", "credits": 4, "dept": "CS",
     "description": "Processes, threads, scheduling, memory management, and file systems."},
    {"code": "MATH201", "title": "Linear Algebra", "credits": 4, "dept": "SCI",
     "description": "Vector spaces, matrices, eigenvalues, and linear transformations."},
    {"code": "MATH110", "title": "Calculus I", "credits": 4, "dept": "SCI",
     "description": "Limits, derivatives, integrals, and the fundamental theorem of calculus."},
    {"code": "CHEM210", "title": "Organic Chemistry I", "credits": 4, "dept": "SCI",
     "description": "Structure, nomenclature, and reactions of organic compounds."},
    {"code": "ENG150", "title": "Shakespearean Literature", "credits": 3, "dept": "AH",
     "description": "Close reading of major tragedies and comedies by William Shakespeare."},
    {"code": "COM220", "title": "Financial Accounting", "credits": 3, "dept": "MGT",
     "description": "Principles of recording, summarizing, and reporting financial transactions."},
]

# course code -> list of prerequisite course codes
PREREQUISITES = {
    "CS501": ["MATH201"],  # ML builds on linear algebra
    "CS420": ["CS310"],
}

ROOMS = [
    {"building": "Main Building", "room_number": "101", "capacity": 60},
    {"building": "Main Building", "room_number": "102", "capacity": 40},
    {"building": "Science Block", "room_number": "201", "capacity": 50},
    {"building": "Science Block", "room_number": "202", "capacity": 30},
]

# course code -> (instructor "First Last", semester, section, day, start, end, building, room)
OFFERINGS = [
    {"course": "CS501", "instructor": "Alan Turing", "semester": "Fall 2026", "section": "A",
     "day": "mon", "start": time(10, 0), "end": time(11, 30), "building": "Main Building", "room": "101"},
    {"course": "CS310", "instructor": "Grace Hopper", "semester": "Fall 2026", "section": "A",
     "day": "tue", "start": time(9, 0), "end": time(10, 30), "building": "Main Building", "room": "102"},
    {"course": "CS420", "instructor": "Grace Hopper", "semester": "Fall 2026", "section": "A",
     "day": "thu", "start": time(14, 0), "end": time(15, 30), "building": "Main Building", "room": "102"},
    {"course": "MATH201", "instructor": "Emmy Noether", "semester": "Fall 2026", "section": "A",
     "day": "wed", "start": time(11, 0), "end": time(12, 30), "building": "Science Block", "room": "201"},
    {"course": "MATH110", "instructor": "Srinivasa Ramanujan", "semester": "Fall 2026", "section": "A",
     "day": "mon", "start": time(9, 0), "end": time(10, 30), "building": "Science Block", "room": "201"},
    {"course": "CHEM210", "instructor": "Marie Curie", "semester": "Fall 2026", "section": "A",
     "day": "fri", "start": time(10, 0), "end": time(11, 30), "building": "Science Block", "room": "202"},
    {"course": "ENG150", "instructor": "Virginia Woolf", "semester": "Fall 2026", "section": "A",
     "day": "tue", "start": time(13, 0), "end": time(14, 30), "building": "Main Building", "room": "101"},
    {"course": "COM220", "instructor": "Adam Smith", "semester": "Fall 2026", "section": "A",
     "day": "wed", "start": time(9, 0), "end": time(10, 30), "building": "Main Building", "room": "102"},
]

# course code -> (exam_date, start, end, building, room)
EXAMS = [
    {"course": "CS501", "date": date(2026, 12, 10), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "101"},
    {"course": "CS310", "date": date(2026, 12, 12), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
    {"course": "CS420", "date": date(2026, 12, 14), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
    {"course": "MATH201", "date": date(2026, 12, 11), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "201"},
    {"course": "MATH110", "date": date(2026, 12, 13), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "201"},
    {"course": "CHEM210", "date": date(2026, 12, 15), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "202"},
    {"course": "ENG150", "date": date(2026, 12, 16), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "101"},
    {"course": "COM220", "date": date(2026, 12, 17), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
]

# program name -> list of (semester, fee_type, amount)
FEES = [
    {"program": "B.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "75000.00"},
    {"program": "B.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Lab", "amount": "10000.00"},
    {"program": "M.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "90000.00"},
    {"program": "B.Sc Mathematics", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "45000.00"},
    {"program": "B.Sc Chemistry", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "48000.00"},
    {"program": "B.Sc Chemistry", "semester": "Fall 2026", "fee_type": "Lab", "amount": "12000.00"},
    {"program": "B.A English", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "40000.00"},
    {"program": "B.Com", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "42000.00"},
]


class Command(DevelopmentOnlyCommand):
    dev_only_reason = "it writes fabricated college records into the database"

    help = "Wipe and reseed the academics tables with a consistent demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help=(
                "Only seed when there is no academics data yet. Use this on "
                "automated startup so a restart never wipes real data that was "
                "loaded after the first boot."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["if_empty"] and Department.objects.exists():
            self.stdout.write("Academics data already present; skipping seed (--if-empty).")
            return

        self._wipe()

        departments = {}
        for d in DEPARTMENTS:
            departments[d["code"]] = Department.objects.create(**d)

        faculty = {}
        for f in FACULTY:
            obj = Faculty.objects.create(
                first_name=f["first"],
                last_name=f["last"],
                email=f"{f['first'].lower()}.{f['last'].lower()}@college.edu",
                designation=f["designation"],
                department=departments[f["dept"]],
                joined_date=date(2015, 1, 1),
            )
            faculty[f"{f['first']} {f['last']}"] = obj

        programs = {}
        for p in PROGRAMS:
            programs[p["name"]] = Program.objects.create(
                name=p["name"],
                degree_level=p["degree_level"],
                department=departments[p["dept"]],
                duration_years=p["duration_years"],
            )

        courses = {}
        for c in COURSES:
            courses[c["code"]] = Course.objects.create(
                code=c["code"],
                title=c["title"],
                credits=c["credits"],
                department=departments[c["dept"]],
                description=c["description"],
            )
        # Wire prerequisites now that all courses exist.
        for code, prereqs in PREREQUISITES.items():
            courses[code].prerequisites.set([courses[p] for p in prereqs])

        rooms = {}
        for r in ROOMS:
            rooms[(r["building"], r["room_number"])] = Room.objects.create(**r)

        offerings = {}
        for o in OFFERINGS:
            offering = CourseOffering.objects.create(
                course=courses[o["course"]],
                instructor=faculty[o["instructor"]],
                semester=o["semester"],
                section=o["section"],
            )
            offerings[o["course"]] = offering
            ClassSchedule.objects.create(
                course_offering=offering,
                day_of_week=o["day"],
                start_time=o["start"],
                end_time=o["end"],
                room=rooms[(o["building"], o["room"])],
            )

        for e in EXAMS:
            ExamTimetable.objects.create(
                course=courses[e["course"]],
                exam_date=e["date"],
                start_time=e["start"],
                end_time=e["end"],
                room=rooms[(e["building"], e["room"])],
            )

        for fee in FEES:
            FeeStructure.objects.create(
                program=programs[fee["program"]],
                semester=fee["semester"],
                fee_type=fee["fee_type"],
                amount=Decimal(fee["amount"]),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {len(departments)} departments, {len(faculty)} faculty, "
            f"{len(programs)} programs, {len(courses)} courses, {len(rooms)} rooms, "
            f"{len(offerings)} offerings, {len(EXAMS)} exams, {len(FEES)} fee rows."
        ))

    def _wipe(self):
        # Delete children before parents to avoid FK violations. Per-student
        # tables are wiped too (they're empty, but keep this a clean reset).
        for model in (
            Attendance, ExamResult, Enrollment, FeePayment, Student,
            ClassSchedule, ExamTimetable, CourseOffering, FeeStructure,
            Course, Program, Faculty, Room, Department,
        ):
            model.objects.all().delete()
