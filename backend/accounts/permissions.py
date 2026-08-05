# Copyright (c) 2026 Yash Garad. All rights reserved.

from rest_framework.permissions import BasePermission

from .models import profile_for


class IsStaffUser(BasePermission):
    """Administrative capability only.

    Since Phase 4 this NO LONGER guards the assistant — students use that too.
    It is retained for genuinely administrative endpoints. Anything gated on it
    should be something a student must not be able to do.
    """

    message = "Staff access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class CanUseAssistant(BasePermission):
    """May ask the assistant a question: any authenticated, active account whose
    initial password has been replaced.

    Three conditions, each for a different reason:

      authenticated  - the assistant reads institutional data and burns local
                       LLM compute; it is never anonymous.
      active         - deactivating an account must lock it out immediately.
                       DRF's SessionAuthentication already rejects inactive
                       users, so this is defence in depth for any other
                       authentication class added later.
      password set   - an account still on its operator-issued password is not
                       yet under the sole control of its owner. Until it is,
                       every action it takes is attributable to two people,
                       which makes the audit log meaningless.
    """

    message = "Not authorised to use the assistant."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False

        if profile_for(user).must_change_password:
            self.message = (
                "You must change your initial password before using the assistant."
            )
            return False

        return True
