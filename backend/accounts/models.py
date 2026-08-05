# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.contrib.auth.models import Group, User
from django.db import models

# Role names. Roles are Django Groups rather than fields so that permissions can
# later be attached to them without another migration.
#
# NOTE ON `is_staff`: it no longer means "may use the assistant" — students use
# it too. It retains its Django meaning of "may administer", and is set only for
# the STAFF role. Anything gated on is_staff is an administrative capability, not
# an assistant one.
ROLE_STAFF = "staff"
ROLE_STUDENT = "student"
ROLES = (ROLE_STAFF, ROLE_STUDENT)


def ensure_groups():
    """Idempotently create the role groups. Called from the entrypoint via
    `manage.py setup_roles` so a fresh database has them before any user
    import runs."""
    return {name: Group.objects.get_or_create(name=name)[0] for name in ROLES}


class UserProfile(models.Model):
    """Per-user state Django's User model has no field for.

    Exists chiefly for `must_change_password`. The alternative — reusing
    `last_login is None` to mean "never logged in, so force a change" — breaks
    the moment a user logs in once and abandons the session, and cannot express
    "an operator reset this password, force another change".
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    # Defaults True: every account created by an operator starts with a
    # password the operator has seen, so the user must replace it before the
    # account can do anything. Cleared by the change-password endpoint.
    must_change_password = models.BooleanField(default=True)

    # UI theme preference, stored SERVER-SIDE on purpose.
    #
    # localStorage would be simpler, but it is per-browser and per-device: the
    # same person on a lab machine, their laptop and their phone would get three
    # different themes, and clearing site data silently resets it. Keeping it on
    # the profile means the preference follows the account.
    THEME_CHOICES = [("light", "Light"), ("dark", "Dark")]
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="dark")

    # --- brute-force lockout ---------------------------------------------------
    # Per-ACCOUNT, and deliberately separate from the per-IP login throttle.
    # They stop different attacks and neither substitutes for the other:
    #
    #   per-IP throttle   caps how fast ONE source can guess. Useless against a
    #                     distributed attempt — 500 hosts each trying twice a
    #                     minute never trip it.
    #   this lockout      caps how many times ONE ACCOUNT can be guessed at,
    #                     from anywhere, by anyone.
    #
    # Stored on the row rather than in the cache on purpose: the cache is
    # per-process local memory, so a restart would clear every lockout, and an
    # attacker who could cause restarts could reset the counter at will.
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Audit trail for account provisioning — who created this account and when.
    # Deliberately a plain CharField rather than a FK: the creating operator's
    # account may later be deleted, and losing the record of who provisioned an
    # account would be worse than a dangling name.
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_profile"

    def __str__(self):
        return f"{self.user.username} (must_change_password={self.must_change_password})"

    @property
    def role(self):
        """The user's role name, derived from group membership."""
        names = set(self.user.groups.values_list("name", flat=True))
        for role in ROLES:
            if role in names:
                return role
        return ""


def profile_for(user):
    """Fetch or lazily create a profile.

    Lazy creation matters for accounts that predate this model — notably the
    bootstrap staff account created by create_staff_user on earlier versions.
    Such an account gets must_change_password=False, because forcing a change on
    an account whose password is set from the environment on every restart would
    produce an unbreakable loop: the user changes it, the next backend restart
    resets it, and the flag is set again.
    """
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={"must_change_password": False, "created_by": "legacy"},
    )
    return profile
