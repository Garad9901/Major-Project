# Copyright (c) 2026 Yash Garad. All rights reserved.

DEGREE_LABELS = {
    "bachelor": "Bachelor's",
    "master": "Master's",
    "diploma": "Diploma",
    "phd": "PhD",
}


def _department_to_text(row, dept_lookup):
    parts = [f"Department: {row['name']} (code: {row['code']})."]
    if row.get("established_year"):
        parts.append(f"Established in {row['established_year']}.")
    return " ".join(parts)


def _faculty_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    parts = [f"{row['first_name']} {row['last_name']} is a faculty member in the {dept_name} department."]
    if row.get("designation"):
        parts.append(f"Designation: {row['designation']}.")
    return " ".join(parts)


def _program_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    degree = DEGREE_LABELS.get(row.get("degree_level"), row.get("degree_level"))
    return (
        f"{row['name']} is a {degree} program offered by the {dept_name} department, "
        f"with a duration of {row['duration_years']} years."
    )


def _course_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    text = f"{row['code']}: {row['title']}. Offered by the {dept_name} department, worth {row['credits']} credits."
    if row.get("description"):
        text += f" {row['description']}"
    return text


def _faculty_development_profile_to_text(row, dept_lookup):
    """Unlike the templates above, this one does almost nothing.

    Those tables hold structured columns that have to be assembled into a
    sentence here. faculty_development_profiles already stores a finished
    paragraph in `body` — the loader that writes the row is what renders the
    prose (see academics/management/commands/load_faculty_dataset.py), because
    the aggregates it summarises are only available on the backend side.

    So all this does is prepend the title, which carries the scope ("by
    department: Computer Science") and measurably helps retrieval: without it,
    the department-level and rank-level paragraphs embed very close together.

    No dept_lookup is needed — the department name is already in the text.
    """
    return f"{row['title']}. {row['body']}"


_TEMPLATES = {
    "departments": _department_to_text,
    "faculty": _faculty_to_text,
    "programs": _program_to_text,
    "courses": _course_to_text,
    "faculty_development_profiles": _faculty_development_profile_to_text,
}


def row_to_text(table, row, dept_lookup):
    return _TEMPLATES[table](row, dept_lookup)
