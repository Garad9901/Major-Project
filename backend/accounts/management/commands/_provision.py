# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Shared account-provisioning logic for create_user and import_users.

Kept in one place so the two commands cannot drift on the security-relevant
parts: password generation, validator enforcement, role assignment and the
must_change_password flag.
"""

import secrets
import string

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import ROLE_STAFF, ROLE_STUDENT, ROLES, ensure_groups

# Ambiguous characters removed. These passwords get printed on paper or read
# aloud, and 0/O, 1/l/I cause failed logins that look like system faults.
_ALPHABET = (
    "".join(c for c in string.ascii_letters if c not in "lIO")
    + "".join(c for c in string.digits if c not in "01")
    + "@#%+=?"
)

# Comfortably above the 12-character minimum validator so a generated password
# is never rejected by our own rules.
INITIAL_PASSWORD_LENGTH = 16


class ProvisionError(Exception):
    pass


def generate_initial_password(length=INITIAL_PASSWORD_LENGTH):
    """Cryptographically random initial password.

    secrets, not random: `random` is a Mersenne Twister seeded from the clock
    and its output is predictable from a few samples. For a value that guards a
    student record, that difference is the whole point.
    """
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def normalise_role(value):
    role = (value or "").strip().lower()
    if role in ("staff", "teacher", "faculty"):
        return ROLE_STAFF
    if role in ("student", "students"):
        return ROLE_STUDENT
    raise ProvisionError(
        f"unknown role {value!r} (expected one of: {', '.join(ROLES)})"
    )


def provision_user(*, username, role, email="", full_name="", created_by="",
                   password=None, groups=None):
    """Create one account. Returns (user, initial_password).

    Raises ProvisionError if the username is taken or the password fails the
    configured validators. Never updates an existing account: silently resetting
    a real person's password because their username appeared twice in a CSV
    would be a live outage for them.
    """
    username = (username or "").strip()
    if not username:
        raise ProvisionError("username is required")

    if User.objects.filter(username__iexact=username).exists():
        raise ProvisionError(f"user {username!r} already exists")

    role = normalise_role(role)
    initial_password = password or generate_initial_password()

    first_name, _, last_name = (full_name or "").strip().partition(" ")

    user = User(
        username=username,
        email=(email or "").strip(),
        first_name=first_name[:150],
        last_name=last_name[:150],
        # is_staff means "may administer", NOT "may use the assistant".
        # Students are legitimate users with is_staff=False.
        is_staff=(role == ROLE_STAFF),
        is_superuser=False,
    )

    # Validate BEFORE hashing and saving, with the user instance attached so the
    # similarity validator can compare against username/name/email.
    try:
        validate_password(initial_password, user=user)
    except ValidationError as exc:
        raise ProvisionError(f"password rejected: {' '.join(exc.messages)}") from None

    user.set_password(initial_password)
    user.save()

    groups = groups if groups is not None else ensure_groups()
    user.groups.add(groups[role])

    # Imported here to avoid a circular import at module load.
    from accounts.models import UserProfile

    UserProfile.objects.create(
        user=user,
        must_change_password=True,
        created_by=created_by or "",
    )

    return user, initial_password
