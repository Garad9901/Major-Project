# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Generate, refresh or report the pre-computed prose answers.

    manage.py precompute_answers --plan        what would be generated, and how long
    manage.py precompute_answers               generate everything missing (install time)
    manage.py precompute_answers --refresh     fingerprints, prune, regenerate changed
    manage.py precompute_answers --status      what is stored, with versions

Runs the FULL pipeline per answer and takes the LLM slot like any request, so
at install time it is run before users arrive. The background refresher in
orchestrator/precompute_refresher.py does the same work continuously but only
when nobody is waiting; this command is the manual, foreground form.

The projected first-run time is printed BEFORE anything starts, from the
measured model-path p50, so nobody watching an install thinks it has hung.
"""

from django.core.management.base import BaseCommand

from orchestrator import concurrency, precompute
from orchestrator.models import PrecomputedAnswer
from sql_agent import db, db_mssql, guard


def _conn_factory():
    return (db_mssql if guard.DIALECT == "tsql" else db).connection


class Command(BaseCommand):
    help = "Generate, refresh or report the pre-computed prose answers."

    def add_arguments(self, parser):
        parser.add_argument("--plan", action="store_true", help="Show the plan and projected time; generate nothing.")
        parser.add_argument("--refresh", action="store_true", help="Prune changed/gone answers and regenerate them.")
        parser.add_argument("--status", action="store_true", help="List what is stored.")
        parser.add_argument("--limit", type=int, default=0, help="Generate at most N answers this run.")

    def handle(self, *args, **opts):
        cf = _conn_factory()

        if opts["status"]:
            rows = PrecomputedAnswer.objects.order_by("shape", "entity_key")
            self.stdout.write(f"{rows.count()} stored answers")
            for r in rows:
                self.stdout.write(
                    f"  {r.shape:32} {r.entity_key or '(global)':40} "
                    f"v{r.data_version[:8]}  {r.generation_ms/1000:5.1f}s  served {r.served_count}"
                )
            return

        p50 = concurrency.measured_model_p50_seconds() or concurrency._FALLBACK_P50_SECONDS
        items = precompute.plan(cf, precompute.observed_pairs_from_audit())
        have = {(p.shape, p.entity_key) for p in PrecomputedAnswer.objects.all()}
        missing = [(s, v) for s, v in items if (s.name, s.key(v)) not in have]

        self.stdout.write(f"planned answers : {len(items)}  (stored {len(have)}, missing {len(missing)})")
        self.stdout.write(f"model-path p50  : {p50:.0f} s (measured from query_profile)")
        self.stdout.write(
            f"projected time  : ~{precompute.projected_first_run(missing, p50)//60} min "
            f"for the {len(missing)} missing answers"
        )
        by_shape = {}
        for s, v in items:
            by_shape.setdefault(s.name, []).append(v)
        for name, vals in by_shape.items():
            self.stdout.write(f"  {name:32} {len(vals):3}  e.g. {vals[0] if vals and vals[0] else '(global)'}")

        if opts["plan"]:
            return

        if opts["refresh"]:
            summary = precompute.refresh(cf, only_when_idle=False, reason="manual refresh")
            self.stdout.write(f"refresh: {summary}")
            return

        limit = opts["limit"] or len(missing)
        done = stored = 0
        for shape, values in missing[:limit]:
            done += 1
            ok, detail = precompute.generate(shape, values, cf, reason="install")
            stored += ok
            self.stdout.write(f"  [{done}/{limit}] {shape.name} {values}: {detail}")
        self.stdout.write(self.style.SUCCESS(
            f"generated {done}, stored {stored}, rejected by verification {done - stored}"
        ))
