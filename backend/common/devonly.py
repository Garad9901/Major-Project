# Copyright (c) 2026 Yash Garad. All rights reserved.

"""One guard for every management command that must never touch production.

WHY ONE, RATHER THAN A CHECK PER COMMAND

There are several dangerous-in-production commands — mirror_to_mssql drops and
recreates tables as `sa`, seed_demo_data writes fabricated records, and the
demo_* commands run agents against whatever database they find. Left to guard
themselves, each invents its own condition, and they end up with three
heuristics of differing quality. mirror_to_mssql's first version checked whether
the HOSTNAME looked like a college server, which is a guess about a string, not
a control.

So: one base class, one test, applied everywhere. A command either declares
itself development-only or it does not.

WHAT IT CHECKS, AND WHY THAT VARIABLE

DJANGO_ENV. Not a hostname pattern, not a DEBUG flag — the same variable that
already selects the settings module, that docker-compose.prod.yml sets
explicitly, and that config/secret_guards.py already trusts to decide whether to
refuse default credentials. If DJANGO_ENV is wrong, far more than this is
already broken, so there is nothing to gain from a second, weaker opinion about
what environment this is.

THIS IS ONE LAYER OF THREE

  1. this guard — refuses on the authoritative switch
  2. absence of credential — SA passwords live only in .env.mssql.local, so on
     production the command cannot function even if it runs. Absence of a
     credential beats a check that has to execute correctly.
  3. build-time exclusion — .dockerignore keeps these out of the image, which
     is the layer that survives the other two being wrong.

No single one of these is trusted alone.
"""

import os

from django.core.management.base import BaseCommand, CommandError


def is_production():
    """True when this process believes it is production.

    Read at call time rather than import time so a test can set the variable
    around a call without reimporting the module.
    """
    return os.getenv("DJANGO_ENV", "development").strip().lower() == "production"


class DevelopmentOnlyCommand(BaseCommand):
    """A management command that refuses to run under DJANGO_ENV=production.

    Subclass instead of BaseCommand and implement `handle` as usual. Do not
    override `execute` — the check runs there rather than in `handle` so that a
    subclass cannot skip it by forgetting to call super().

    Set `dev_only_reason` to say what the command would DO to production. The
    message an operator sees should explain the risk, not just announce a
    refusal, because the next thing a blocked operator does is look for the way
    around it.
    """

    dev_only_reason = "it modifies data in ways that are unsafe outside development"

    def execute(self, *args, **options):
        if is_production():
            raise CommandError(
                f"{self.__class__.__module__.rsplit('.', 1)[-1]} is a "
                f"DEVELOPMENT-ONLY command and DJANGO_ENV=production: "
                f"{self.dev_only_reason}.\n"
                "If you are certain this is not a production system, the "
                "environment variable is wrong — fix that rather than working "
                "around this check, because the same variable decides which "
                "settings module loads and whether default credentials are "
                "refused."
            )
        return super().execute(*args, **options)
