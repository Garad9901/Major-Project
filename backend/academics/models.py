# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.db import models

# ============================================================================
# General institutional data — safe for the read-only RAG agent
# (rag_agent_ro is granted SELECT on these tables; see db/sql/create_rag_agent_ro.sql)
# ============================================================================


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=10, unique=True)
    established_year = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "departments"

    def __str__(self):
        return self.name


class Faculty(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, related_name="faculty_members"
    )
    joined_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faculty"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Program(models.Model):
    DEGREE_CHOICES = [
        ("bachelor", "Bachelor's"),
        ("master", "Master's"),
        ("diploma", "Diploma"),
        ("phd", "PhD"),
    ]
    name = models.CharField(max_length=150)
    degree_level = models.CharField(max_length=20, choices=DEGREE_CHOICES)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="programs")
    duration_years = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "programs"

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    credits = models.PositiveSmallIntegerField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="courses")
    description = models.TextField(blank=True)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="required_for"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "courses"

    def __str__(self):
        return f"{self.code} - {self.title}"


class Room(models.Model):
    building = models.CharField(max_length=100)
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rooms"
        unique_together = ("building", "room_number")

    def __str__(self):
        return f"{self.building} {self.room_number}"


class CourseOffering(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="offerings")
    instructor = models.ForeignKey(
        Faculty, on_delete=models.SET_NULL, null=True, related_name="course_offerings"
    )
    semester = models.CharField(max_length=20)
    section = models.CharField(max_length=10, default="A")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "course_offerings"
        unique_together = ("course", "semester", "section")

    def __str__(self):
        return f"{self.course.code} [{self.semester} {self.section}]"


class ClassSchedule(models.Model):
    DAY_CHOICES = [
        ("mon", "Monday"),
        ("tue", "Tuesday"),
        ("wed", "Wednesday"),
        ("thu", "Thursday"),
        ("fri", "Friday"),
        ("sat", "Saturday"),
    ]
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="schedule_slots"
    )
    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name="class_schedules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_schedule"

    def __str__(self):
        return f"{self.course_offering} {self.day_of_week} {self.start_time}-{self.end_time}"


class ExamTimetable(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exam_slots")
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name="exam_slots")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exam_timetable"

    def __str__(self):
        return f"{self.course.code} exam on {self.exam_date}"


class FeeStructure(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="fee_structures")
    semester = models.CharField(max_length=20)
    fee_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    # The unit for `amount`. Added because a bare number has no currency, and
    # the model filled the gap by guessing: it reported the B.Tech tuition fee
    # as "$75,000.00" for an Indian college. The figure was right and the symbol
    # was invented — which is worse than being vague, because it reads as
    # authoritative. Data carries its own units now.
    currency = models.CharField(max_length=3, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fee_structure"

    def __str__(self):
        return f"{self.program} {self.semester} {self.fee_type}"


# ============================================================================
# Per-student data — NOT granted to rag_agent_ro. Personal/sensitive:
# identity, academic performance, attendance, and payment history.
# ============================================================================


class Student(models.Model):
    roll_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, related_name="students")
    batch_year = models.PositiveIntegerField()

    class Meta:
        db_table = "students"

    def __str__(self):
        return f"{self.roll_number} - {self.first_name} {self.last_name}"


class Enrollment(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("completed", "Completed"), ("dropped", "Dropped")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    enrolled_on = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "enrollments"
        unique_together = ("student", "course_offering")

    def __str__(self):
        return f"{self.student.roll_number} -> {self.course_offering}"


class Attendance(models.Model):
    STATUS_CHOICES = [("present", "Present"), ("absent", "Absent"), ("excused", "Excused")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "attendance"
        unique_together = ("enrollment", "date")


class ExamResult(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="exam_results")
    exam_type = models.CharField(max_length=50)
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2)
    grade = models.CharField(max_length=5, blank=True)

    class Meta:
        db_table = "exam_results"


class FeePayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="fee_payments")
    fee_structure = models.ForeignKey(
        FeeStructure, on_delete=models.SET_NULL, null=True, related_name="payments"
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    status = models.CharField(max_length=20, default="paid")

    class Meta:
        db_table = "fee_payments"


# ============================================================================
# Real imported dataset — faculty development survey
# ============================================================================
# Source: a Kaggle CSV of anonymised faculty professional-development metrics
# (13,000 rows, 34 columns, no personal identifiers — the subject key is an
# opaque "FAC_00001" style code). Loaded by:
#
#     python manage.py load_faculty_dataset --csv <path>
#
# THIS IS NOT THE SAME ENTITY AS THE `Faculty` MODEL ABOVE.
# `Faculty` is the college's own staff directory: named people, emails, a
# department foreign key. This is an anonymised analytics snapshot with no
# names and no way to join back to a real person. They are deliberately kept as
# separate tables rather than merged, because merging would imply a
# relationship between a survey row and a named employee that the data does not
# support.
#
# WHY `department` IS PLAIN TEXT AND NOT A FOREIGN KEY
# The dataset carries its own eight-value department vocabulary ("Computer
# Science", "Arts and Humanities", ...) which is not the college's department
# list and has no shared key with it. Coercing it into a FK would mean
# inventing rows in `departments` that the college does not actually have. It
# is kept as the CSV's own text value, which is also what makes the SQL agent's
# job simple: counting by department needs no JOIN.
# ============================================================================


class FacultyDevelopment(models.Model):
    """One row per anonymised faculty record in the imported survey.

    DELIBERATELY HAS NO `updated_at` COLUMN.
    The sync worker discovers what to poll by looking for an `updated_at`
    watermark (see sync_worker/config.py). This table is a static bulk-loaded
    snapshot of 13,000 rows with no free-text column worth vector search, so
    polling it would queue 13,000 change events for no benefit and embedding it
    would be 13,000 pointless embedding calls. Omitting the watermark excludes
    it structurally rather than by a flag someone can forget to set. The
    exclusion is named in sync_worker/config.EXPECTED_EXCLUSIONS so the worker
    reports it as an expected decision instead of warning about it.

    Semantic search over this data is served by FacultyDevelopmentProfile
    below, which holds a few dozen prose summaries rather than 13,000 rows of
    numbers.
    """

    # The CSV's own identifier ("FAC_00001"). Unique across all 13,000 rows and
    # never blank, so it is the real primary key rather than a surrogate — this
    # is also what makes re-running the loader an upsert instead of a duplicate.
    faculty_id = models.CharField(max_length=20, primary_key=True)

    # --- demographics / experience ---
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=10)
    academic_rank = models.CharField(max_length=30)
    teaching_experience_years = models.PositiveSmallIntegerField()
    research_experience_years = models.PositiveSmallIntegerField()
    department = models.CharField(max_length=50, db_index=True)
    university_type = models.CharField(max_length=20)

    # --- institutional context (0-100 scores) ---
    institution_digital_infrastructure = models.DecimalField(max_digits=5, decimal_places=2)
    institutional_support_score = models.DecimalField(max_digits=5, decimal_places=2)
    big_data_readiness_score = models.DecimalField(max_digits=5, decimal_places=2)

    # --- digital teaching practice ---
    lms_usage_frequency = models.CharField(max_length=20)
    online_teaching_hours_per_week = models.DecimalField(max_digits=4, decimal_places=1)
    digital_tool_usage_score = models.DecimalField(max_digits=5, decimal_places=2)
    data_literacy_score = models.DecimalField(max_digits=5, decimal_places=2)
    ai_tool_adoption_score = models.DecimalField(max_digits=5, decimal_places=2)

    # --- TRACK competency framework (0-100 scores) ---
    track_technology_knowledge = models.DecimalField(max_digits=5, decimal_places=2)
    track_research_analytics_knowledge = models.DecimalField(max_digits=5, decimal_places=2)
    track_academic_content_knowledge = models.DecimalField(max_digits=5, decimal_places=2)
    track_collaborative_knowledge = models.DecimalField(max_digits=5, decimal_places=2)
    track_knowledge_integration = models.DecimalField(max_digits=5, decimal_places=2)

    # --- teaching outcomes ---
    student_feedback_score = models.DecimalField(max_digits=5, decimal_places=2)
    teaching_effectiveness_score = models.DecimalField(max_digits=5, decimal_places=2)

    # --- research output ---
    research_publications = models.PositiveSmallIntegerField()
    research_productivity_score = models.DecimalField(max_digits=5, decimal_places=2)
    publication_quality_index = models.DecimalField(max_digits=5, decimal_places=2)

    # --- professional development ---
    training_programs_attended = models.PositiveSmallIntegerField()
    professional_development_score = models.DecimalField(max_digits=5, decimal_places=2)
    collaboration_index = models.DecimalField(max_digits=5, decimal_places=2)
    innovation_in_teaching_score = models.DecimalField(max_digits=5, decimal_places=2)
    administrative_participation_score = models.DecimalField(max_digits=5, decimal_places=2)

    # --- assessed outcome ---
    overall_faculty_development_index = models.DecimalField(max_digits=5, decimal_places=2)
    competency_level = models.CharField(max_length=20, db_index=True)
    # The dataset's label column: the assessed development need for this person.
    target = models.CharField(max_length=30, db_index=True)

    # NOT a sync watermark — records when the bulk load last touched this row,
    # for operator troubleshooting only. Named `loaded_at` rather than
    # `updated_at` precisely so it cannot be mistaken for one by the poller.
    loaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faculty_development"
        indexes = [
            models.Index(fields=["department", "academic_rank"]),
        ]

    def __str__(self):
        return f"{self.faculty_id} ({self.department}, {self.academic_rank})"


class FacultyDevelopmentProfile(models.Model):
    """A short prose summary of one slice of the faculty development dataset.

    WHAT THIS IS, HONESTLY
    The numbers in `body` are REAL — every figure is a live SQL aggregate over
    the 13,000 imported rows. The PROSE AROUND THEM IS SYNTHETIC: generated by
    a fixed Python f-string template in the loader, not written by anyone and
    not part of the source dataset.

    It exists because the imported dataset is entirely numeric and categorical,
    so there is nothing in it for a vector search to retrieve. Rather than skip
    the RAG half of the system in this test, the loader renders aggregates into
    readable paragraphs so the embedding -> Qdrant -> retrieval path has real
    content flowing through it.

    A production RAG corpus would be human-written prose (handbooks, policies,
    course descriptions). This is not that, and should not be presented as
    evidence of retrieval quality on natural text — only as evidence that the
    pipeline works.

    Unlike FacultyDevelopment above, this table DOES carry created_at/updated_at
    so the sync worker picks it up and embeds it through the normal path.
    """

    # Which dimension this summary covers: "department", "academic_rank",
    # "university_type", "competency_level", "lms_usage", "department_rank".
    scope = models.CharField(max_length=40)
    # The value within that dimension, e.g. "Computer Science", or
    # "Computer Science / Professor" for the crossed scope.
    scope_key = models.CharField(max_length=120)
    title = models.CharField(max_length=200)
    body = models.TextField()
    faculty_count = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faculty_development_profiles"
        unique_together = ("scope", "scope_key")

    def __str__(self):
        return self.title
