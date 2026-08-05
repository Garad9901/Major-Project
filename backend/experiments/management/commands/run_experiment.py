# Copyright (c) 2026 Yash Garad. All rights reserved.

import csv
import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from experiments import runner, similarity
from experiments.warmup import warm_up_models

DEFAULT_QA_PATH = "experiments/fixtures/sample_qa.json"
DEFAULT_OUTPUT_DIR = "experiment_results"


class Command(BaseCommand):
    help = (
        "Runs a set of ground-truth Q/A pairs through the full pipeline under "
        "three configurations (full swarm, RAG-only, SQL-only), scores each "
        "answer against ground truth, and exports per-run results to CSV "
        "(plus a JSONL sidecar with the full nested detail). Results are "
        "written incrementally so a long run survives interruption."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--qa-file",
            default=DEFAULT_QA_PATH,
            help="Path to a JSON file: [{\"question\": ..., \"answer\": ...}, ...]",
        )
        parser.add_argument(
            "--configs",
            default=",".join(runner.CONFIGS),
            help=f"Comma-separated subset of: {', '.join(runner.CONFIGS)}",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=similarity.DEFAULT_THRESHOLD,
            help="Semantic-similarity threshold for marking an answer correct.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only run the first N Q/A pairs (handy for a quick smoke test).",
        )
        parser.add_argument(
            "--output-dir",
            default=DEFAULT_OUTPUT_DIR,
            help="Directory for the CSV + JSONL outputs.",
        )
        parser.add_argument(
            "--tag",
            default=None,
            help="Optional label included in the output filenames.",
        )
        parser.add_argument(
            "--no-warmup",
            action="store_true",
            help="Skip the model warm-up pass (leave cold-start time in latency).",
        )

    def handle(self, *args, **options):
        qa_pairs = self._load_qa(options["qa_file"])
        if options["limit"]:
            qa_pairs = qa_pairs[: options["limit"]]

        configs = [c.strip() for c in options["configs"].split(",") if c.strip()]
        for c in configs:
            if c not in runner.CONFIGS:
                raise CommandError(f"unknown config {c!r}; valid: {', '.join(runner.CONFIGS)}")

        os.makedirs(options["output_dir"], exist_ok=True)
        # timezone.utc rather than Date.now-style calls; deterministic-ish name.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag = f"_{options['tag']}" if options["tag"] else ""
        csv_path = os.path.join(options["output_dir"], f"experiment{tag}_{stamp}.csv")
        jsonl_path = os.path.join(options["output_dir"], f"experiment{tag}_{stamp}.jsonl")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Running {len(qa_pairs)} Q/A pairs x {len(configs)} configs "
                f"= {len(qa_pairs) * len(configs)} pipeline runs"
            )
        )
        self.stdout.write(f"  configs: {', '.join(configs)}")
        self.stdout.write(f"  threshold: {options['threshold']}")
        self.stdout.write(f"  CSV:   {csv_path}")
        self.stdout.write(f"  JSONL: {jsonl_path}\n")

        if not options["no_warmup"]:
            self.stdout.write("Warming up models (excluded from latency)…")
            warm_up_models()

        # Per-config running tallies for the end-of-run summary.
        tally = {c: {"total": 0, "correct": 0, "latency_ms": [], "verif_fail": 0} for c in configs}

        with open(csv_path, "w", newline="", encoding="utf-8") as csv_file, \
                open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
            writer = csv.DictWriter(csv_file, fieldnames=runner.CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            for i, pair in enumerate(qa_pairs, 1):
                question = pair["question"]
                ground_truth = pair["answer"]
                for config in configs:
                    row = runner.run_one(config, question, ground_truth, threshold=options["threshold"])

                    writer.writerow(row)
                    csv_file.flush()  # survive interruption mid-run
                    jsonl_file.write(json.dumps(row) + "\n")
                    jsonl_file.flush()

                    t = tally[config]
                    t["total"] += 1
                    t["correct"] += 1 if row["correct"] == "yes" else 0
                    if row["latency_ms"] is not None:
                        t["latency_ms"].append(row["latency_ms"])
                    if row["verification_flag"] == "fail":
                        t["verif_fail"] += 1

                    flag = "OK " if row["correct"] == "yes" else "XX "
                    err = f"  ERROR: {row['error']}" if row["error"] else ""
                    self.stdout.write(
                        f"  [{i}/{len(qa_pairs)}] {config:<9} {flag} "
                        f"route={row['route_used']} sim={row['semantic_similarity']} "
                        f"verif={row['verification_flag']} {row['latency_ms']}ms{err}"
                    )

        self._print_summary(tally, csv_path)

    def _load_qa(self, path):
        if not os.path.exists(path):
            raise CommandError(
                f"QA file not found: {path}. Provide one with --qa-file pointing to a JSON "
                'list of {"question": ..., "answer": ...} objects.'
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            raise CommandError("QA file must be a non-empty JSON list.")
        for i, item in enumerate(data):
            if "question" not in item or "answer" not in item:
                raise CommandError(f"QA item {i} is missing 'question' or 'answer'.")
        return data

    def _print_summary(self, tally, csv_path):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary by configuration ==="))
        for config, t in tally.items():
            n = t["total"] or 1
            acc = 100.0 * t["correct"] / n
            lat = t["latency_ms"]
            avg_lat = sum(lat) / len(lat) if lat else 0
            self.stdout.write(
                f"  {config:<9} accuracy={acc:5.1f}% ({t['correct']}/{t['total']})  "
                f"avg_latency={avg_lat:8.0f}ms  verification_fails={t['verif_fail']}"
            )
        self.stdout.write(self.style.SUCCESS(f"\nWrote results to {csv_path}"))
