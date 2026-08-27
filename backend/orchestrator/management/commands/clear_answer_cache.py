# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Clear cached answers after the records behind them change.

WHY THIS DOES NOT SIMPLY CALL invalidate().

The answer cache is module-level state inside the SERVING process. A management
command is a different process, so calling orchestrator.cache.invalidate() here
would clear this command's own empty cache, print a cheerful number, and leave
the gunicorn worker serving the old answers. Measured on the running stack:

    ask #1 (cold)                                60 s
    a separate process reports                    0 entries
    ask #2                                        1 s   <- the worker HAS it
    invalidate() from a separate process   "cleared 0 entries"
    ask #3                                        0 s   <- still stale

So invalidation goes through a generation token in Redis, which every serving
process checks on its next lookup. See orchestrator/cache.py.
"""

from django.core.management.base import BaseCommand

from orchestrator import cache


class Command(BaseCommand):
    help = (
        "Clear cached answers across every serving process. Run after importing "
        "or correcting records — answers are matched semantically, so a "
        "rephrased question will otherwise keep hitting the old entry."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reason", default="manual",
            help="Recorded in the log next to the invalidation, so an operator "
                 "reading it later knows why the cache was cleared.",
        )

    def handle(self, *args, **options):
        token = cache.bump_generation(options["reason"])

        if token is None:
            # Redis is how the signal travels. Without it nothing was cleared,
            # and saying otherwise would be exactly the false success this
            # command exists to avoid.
            self.stderr.write(self.style.ERROR(
                "COULD NOT CLEAR THE CACHE: Redis is unreachable, and the "
                "signal has nowhere to travel."
            ))
            self.stderr.write(
                "Cached answers are still being served. Fix Redis and run this "
                "again, or restart the backend to clear it the blunt way:\n"
                "    docker compose up -d --force-recreate backend"
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            "Cached answers cleared across all serving processes."
        ))
        self.stdout.write(
            "Each process drops its entries on its next lookup, so the next "
            "question after this is answered from the records."
        )
