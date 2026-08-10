# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Where the time goes, over the last N questions actually asked.

    python manage.py latency_report                 # last 100
    python manage.py latency_report --last 250
    python manage.py latency_report --route SQL     # one route only
    python manage.py latency_report --exclude-cached

Reads orchestrator.QueryProfile, which is written for every answered question.
Reports percentiles rather than means throughout: latency on CPU inference has a
long right tail, and a mean sits above most requests while describing none of
them.
"""

import statistics

from django.core.management.base import BaseCommand

from orchestrator.models import QueryProfile

STAGES = [
    ("cache_lookup", "Cache lookup", None),
    ("slot_wait", "Slot wait", None),
    ("router", "Router", "router_ms"),
    ("sql", "SQL agent", "sql_ms"),
    ("rag", "RAG agent", "rag_ms"),
    ("web_fetch", "Web fetch", "web_ms"),
    ("synthesis", "Synthesis", "synthesis_ms"),
    ("verification", "Verification", "verification_ms"),
]


def pct(values, p):
    """The p-th percentile, nearest-rank.

    Nearest-rank rather than interpolated so that every number printed is a
    value that a real request actually produced. An interpolated p99 over 100
    samples is an average of two requests, which is a strange thing to quote as
    a worst case.
    """
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(p / 100.0 * len(ordered) + 0.5)) - 1))
    return ordered[k]


def fmt(ms):
    if ms is None:
        return "     –"
    if ms >= 10_000:
        return f"{ms / 1000:5.1f}s"
    return f"{ms:5.0f}ms"


class Command(BaseCommand):
    help = "Per-stage latency percentiles over the most recent questions."

    def add_arguments(self, parser):
        parser.add_argument("--last", type=int, default=100)
        parser.add_argument("--route", default=None, help="SQL / RAG / BOTH / WEB")
        parser.add_argument(
            "--exclude-cached", action="store_true",
            help="Ignore cache hits, to see the cost of actually generating.",
        )
        parser.add_argument(
            "--since-id", type=int, default=None,
            help="Only profiles with id > this. Use to scope a report to one run.",
        )

    def handle(self, *args, **opts):
        qs = QueryProfile.objects.all()
        if opts["route"]:
            qs = qs.filter(route=opts["route"].upper())
        if opts["exclude_cached"]:
            qs = qs.filter(cached="")
        if opts["since_id"]:
            qs = qs.filter(id__gt=opts["since_id"])
        rows = list(qs[: opts["last"]])

        if not rows:
            self.stdout.write("No profiles recorded yet.")
            return

        self.stdout.write("=" * 78)
        self.stdout.write(
            f"LATENCY over the last {len(rows)} question(s)"
            + (f", route={opts['route'].upper()}" if opts["route"] else "")
            + (", cache hits excluded" if opts["exclude_cached"] else "")
        )
        self.stdout.write(
            f"  ids {rows[-1].id}-{rows[0].id}   "
            f"{rows[-1].created_at:%Y-%m-%d %H:%M} to {rows[0].created_at:%Y-%m-%d %H:%M}"
        )
        self.stdout.write("=" * 78)

        self._route_mix(rows)
        self._totals(rows)
        self._stage_table(rows)
        self._tokens(rows)
        self._targets(rows)
        self._worst(rows)

    # -- sections ---------------------------------------------------------

    def _route_mix(self, rows):
        counts = {}
        for r in rows:
            counts[r.route or "?"] = counts.get(r.route or "?", 0) + 1
        cached = sum(1 for r in rows if r.cached)
        mix = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        self.stdout.write(f"\nRoute mix: {mix}   cache hits: {cached}/{len(rows)}")

        tiers = {}
        for r in rows:
            if r.verification_tier:
                tiers[r.verification_tier] = tiers.get(r.verification_tier, 0) + 1
        if tiers:
            self.stdout.write(
                "Verification tier: "
                + "  ".join(f"{k}={v}" for k, v in sorted(tiers.items()))
            )

    def _totals(self, rows):
        totals = [r.total_ms for r in rows if r.total_ms is not None]
        ttfts = [r.ttft_ms for r in rows if r.ttft_ms is not None]
        self.stdout.write("\n" + "-" * 78)
        self.stdout.write(f"{'':22}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}")
        self.stdout.write("-" * 78)
        for label, values in (("END TO END", totals), ("TIME TO FIRST TOKEN", ttfts)):
            self.stdout.write(
                f"{label:22}{fmt(pct(values, 50)):>9}{fmt(pct(values, 95)):>9}"
                f"{fmt(pct(values, 99)):>9}{fmt(max(values) if values else None):>9}"
            )

    def _stage_table(self, rows):
        """Per-stage percentiles, plus each stage's share of the median request.

        The share is computed against the median total rather than by summing
        the medians: the stages do not all occur on every question, so their
        medians do not add up to anything meaningful.
        """
        median_total = pct([r.total_ms for r in rows], 50) or 1
        self.stdout.write("\n" + "-" * 78)
        self.stdout.write(
            f"{'STAGE':22}{'n':>5}{'p50':>9}{'p95':>9}{'p99':>9}{'% of p50 total':>16}"
        )
        self.stdout.write("-" * 78)

        for key, label, column in STAGES:
            if column:
                values = [getattr(r, column) for r in rows if getattr(r, column) is not None]
            else:
                values = [
                    s["ms"]
                    for r in rows
                    for s in (r.stages or {}).get("stages", [])
                    if s["name"] == key
                ]
            if not values:
                continue
            share = (pct(values, 50) or 0) / median_total * 100
            self.stdout.write(
                f"{label:22}{len(values):>5}{fmt(pct(values, 50)):>9}"
                f"{fmt(pct(values, 95)):>9}{fmt(pct(values, 99)):>9}{share:>15.1f}%"
            )

        overheads = [r.overhead_ms for r in rows if r.overhead_ms is not None]
        share = (pct(overheads, 50) or 0) / median_total * 100
        self.stdout.write(
            f"{'Unattributed*':22}{len(overheads):>5}{fmt(pct(overheads, 50)):>9}"
            f"{fmt(pct(overheads, 95)):>9}{fmt(pct(overheads, 99)):>9}{share:>15.1f}%"
        )
        self.stdout.write(
            "\n  * network, JSON serialisation, SSE writes, audit and history inserts —\n"
            "    everything not inside a named stage. An upper bound on what faster\n"
            "    plumbing could ever save."
        )

    def _tokens(self, rows):
        """Prompt reading versus generation, which have different fixes.

        Reading is reduced by shortening prompts; generating is reduced by
        writing less or by faster hardware. Reporting one number for "LLM time"
        hides which lever applies.
        """
        fresh = [r for r in rows if not r.cached and r.gen_ms]
        if not fresh:
            return
        self.stdout.write("\n" + "-" * 78)
        self.stdout.write("WHERE THE LLM TIME GOES (generated answers only)")
        self.stdout.write("-" * 78)
        for label, ms_attr, tok_attr in (
            ("Reading prompts", "prompt_ms", "prompt_tokens"),
            ("Generating output", "gen_ms", "gen_tokens"),
        ):
            ms = [getattr(r, ms_attr) for r in fresh if getattr(r, ms_attr)]
            tok = [getattr(r, tok_attr) for r in fresh if getattr(r, tok_attr)]
            rate = (
                statistics.median([
                    getattr(r, tok_attr) / (getattr(r, ms_attr) / 1000)
                    for r in fresh
                    if getattr(r, ms_attr) and getattr(r, tok_attr)
                ])
                if tok else 0
            )
            self.stdout.write(
                f"{label:22}p50 {fmt(pct(ms, 50))}   p50 tokens {pct(tok, 50):>6}"
                f"   {rate:5.1f} tok/s"
            )

    def _targets(self, rows):
        """Explicit pass/fail against the stated targets.

        Printed as counts rather than a verdict so a partial result is visible:
        "12 of 100" is information, "FAIL" is not.
        """
        ttfts = [r.ttft_ms for r in rows if r.ttft_ms is not None]
        totals = [r.total_ms for r in rows if r.total_ms is not None]
        self.stdout.write("\n" + "-" * 78)
        self.stdout.write("AGAINST THE TARGETS")
        self.stdout.write("-" * 78)
        if ttfts:
            hit = sum(1 for v in ttfts if v <= 2000)
            self.stdout.write(
                f"  first token within 2s : {hit}/{len(ttfts)} ({hit / len(ttfts) * 100:.0f}%)"
            )
        if totals:
            hit = sum(1 for v in totals if v <= 5000)
            self.stdout.write(
                f"  complete within 5s    : {hit}/{len(totals)} ({hit / len(totals) * 100:.0f}%)"
            )
        sql_rows = [r for r in rows if r.route == "SQL" and not r.cached]
        if sql_rows:
            vals = [r.total_ms for r in sql_rows]
            hit = sum(1 for v in vals if v <= 5000)
            self.stdout.write(
                f"  simple (SQL) within 5s: {hit}/{len(vals)} ({hit / len(vals) * 100:.0f}%)"
                f"   p50 {fmt(pct(vals, 50))}"
            )

    def _worst(self, rows, n=5):
        self.stdout.write("\n" + "-" * 78)
        self.stdout.write(f"SLOWEST {n}")
        self.stdout.write("-" * 78)
        for r in sorted(rows, key=lambda r: r.total_ms or 0, reverse=True)[:n]:
            parts = " ".join(
                f"{s['name']}={s['ms'] / 1000:.1f}s"
                for s in sorted(
                    (r.stages or {}).get("stages", []), key=lambda s: -s["ms"]
                )[:4]
            )
            self.stdout.write(
                f"  {r.total_ms / 1000:6.1f}s [{r.route or '?':4}] {r.question[:44]!r}"
            )
            self.stdout.write(f"          {parts}")
