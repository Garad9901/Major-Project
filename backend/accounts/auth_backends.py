# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Authentication backend that survives a database outage for EXISTING sessions.

Only `get_user` is overridden — the per-request "who is this?" lookup that
AuthenticationMiddleware performs. `authenticate()` is untouched and still goes
straight to Postgres, because verifying a password against a store you cannot
read is not something to work around: a NEW sign-in during a database outage
must fail, and does.

See accounts/identity.py for the security reasoning behind the fallback, in
particular why the database is always consulted first.
"""

import logging

from django.contrib.auth.backends import ModelBackend
from django.db import DatabaseError

from . import identity

logger = logging.getLogger("accounts")


class CachedModelBackend(ModelBackend):
    def get_user(self, user_id):
        try:
            user = super().get_user(user_id)
        except DatabaseError as exc:
            # THE OUTAGE PATH. Serve the identity captured on an earlier,
            # successful request so the rest of the pipeline can run and the
            # user gets the degraded answer the orchestrator is built to give.
            user = identity.recall(user_id)
            if user is None:
                logger.warning(
                    "database down and no cached identity for user_id=%s — "
                    "this request cannot be authenticated (%s)", user_id, exc,
                )
                return None
            logger.info(
                "database down — authenticated user_id=%s from cached identity", user_id
            )
            # ModelBackend.get_user applies this check and it must not be lost
            # just because the row came from a different place.
            return user if self.user_can_authenticate(user) else None

        if user is not None:
            # Refresh the fallback copy from the live row on every successful
            # read, so what is cached is never older than the last request this
            # user made while the database was healthy.
            identity.remember(user)
        return user
