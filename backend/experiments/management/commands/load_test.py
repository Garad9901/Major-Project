# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.core.management.base import BaseCommand, CommandError

DEFAULT_QA_PATH = "experiments/fixtures/sample_qa.json"


class Command(BaseCommand):
    help = (
        "Fires N concurrent questions at /api/ask/ over real HTTP and reports "
        "response-time statistics — time-to-first-token (TTFT) and total time "
        "to stream the full answer — so you can see how latency behaves when "
        "multiple management users hit the assistant simultaneously."
    )

    def add_arguments(self, parser):
        parser.add_argument("--concurrency", type=int, default=20, help="Number of simultaneous requests.")
        parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
        parser.add_argument("--username", default=os.getenv("STAFF_USERNAME", "staff"))
        parser.add_argument("--password", default=os.getenv("STAFF_PASSWORD", "staffpass123"))
        parser.add_argument("--qa-file", default=DEFAULT_QA_PATH, help="Question source (cycled to fill concurrency).")
        parser.add_argument("--timeout", type=int, default=600, help="Per-request timeout (seconds).")

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        token = self._login(base_url, options["username"], options["password"])
        questions = self._questions(options["qa_file"], options["concurrency"])
        n = len(questions)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Firing {n} concurrent requests at {base_url}/api/ask/"
        ))

        wall_start = time.perf_counter()
        results = [None] * n
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(self._one_request, base_url, token, q, options["timeout"], i): i
                for i, q in enumerate(questions)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                results[i] = fut.result()
        wall_total = time.perf_counter() - wall_start

        self._report(results, wall_total)

    def _login(self, base_url, username, password):
        try:
            resp = requests.post(
                f"{base_url}/api/auth/login/",
                json={"username": username, "password": password},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CommandError(f"could not reach backend to log in: {exc}")
        if resp.status_code != 200:
            raise CommandError(f"login failed ({resp.status_code}): {resp.text[:200]}")
        return resp.json()["token"]

    def _questions(self, path, concurrency):
        if not os.path.exists(path):
            raise CommandError(f"QA file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pool = [item["question"] for item in data]
        if not pool:
            raise CommandError("QA file has no questions.")
        # Cycle through the available questions to reach the requested count.
        return [pool[i % len(pool)] for i in range(concurrency)]

    def _one_request(self, base_url, token, question, timeout, idx):
        result = {
            "idx": idx,
            "question": question,
            "ok": False,
            "status": None,
            "ttft_ms": None,
            "total_ms": None,
            "tokens": 0,
            "error": None,
        }
        start = time.perf_counter()
        try:
            resp = requests.post(
                f"{base_url}/api/ask/",
                headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
                json={"question": question},
                stream=True,
                timeout=timeout,
            )
            result["status"] = resp.status_code
            if resp.status_code != 200:
                result["error"] = resp.text[:200]
                return result

            first_token_at = None
            saw_error = False
            error_msg = None
            expecting = None  # tracks the event: of the frame whose data: is next
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("event:"):
                    expecting = line[len("event:"):].strip()
                    if expecting == "token" and first_token_at is None:
                        first_token_at = time.perf_counter()
                elif line.startswith("data:"):
                    if expecting == "token" and '"text"' in line:
                        result["tokens"] += 1
                    elif expecting == "error":
                        # The pipeline can stream a server-side error mid-stream
                        # (HTTP is already 200 by then) — a 0-token "success"
                        # would otherwise hide a real under-load failure.
                        saw_error = True
                        error_msg = line[len("data:"):].strip()[:200]

            end = time.perf_counter()
            result["ttft_ms"] = round((first_token_at - start) * 1000, 1) if first_token_at else None
            result["total_ms"] = round((end - start) * 1000, 1)
            if saw_error:
                result["error"] = f"stream error event: {error_msg}"
                result["ok"] = False
            elif result["tokens"] == 0:
                result["error"] = "no tokens streamed (empty answer)"
                result["ok"] = False
            else:
                result["ok"] = True
        except requests.RequestException as exc:
            result["error"] = str(exc)
            result["total_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return result

    def _report(self, results, wall_total):
        self.stdout.write(self.style.MIGRATE_HEADING("\nPer-request results:"))
        self.stdout.write(f"  {'#':>3} {'status':>6} {'TTFT(ms)':>10} {'total(ms)':>11} {'tokens':>7}  question")
        for r in sorted(results, key=lambda x: x["idx"]):
            flag = "" if r["ok"] else f"  ERROR: {r['error']}"
            ttft = r["ttft_ms"] if r["ttft_ms"] is not None else "-"
            self.stdout.write(
                f"  {r['idx']:>3} {str(r['status']):>6} {str(ttft):>10} "
                f"{str(r['total_ms']):>11} {r['tokens']:>7}  {r['question'][:45]}{flag}"
            )

        ok = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary ==="))
        self.stdout.write(f"  requests:      {len(results)}  (ok={len(ok)}, failed={len(failed)})")
        self.stdout.write(f"  wall-clock:    {wall_total * 1000:.0f} ms for the whole batch")

        if ok:
            self._stat_block("time-to-first-token (TTFT)", [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None])
            self._stat_block("total response time", [r["total_ms"] for r in ok])
            throughput = len(ok) / wall_total if wall_total else 0
            self.stdout.write(f"\n  throughput:    {throughput:.2f} completed requests/sec under load")

        if failed:
            self.stdout.write(self.style.ERROR(f"\n  {len(failed)} request(s) failed — see per-request rows above."))

    def _stat_block(self, label, values):
        if not values:
            return
        vals = sorted(values)
        p95 = vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
        self.stdout.write(f"\n  {label}:")
        self.stdout.write(f"    min={min(vals):.0f}  mean={statistics.mean(vals):.0f}  "
                          f"median={statistics.median(vals):.0f}  p95={p95:.0f}  max={max(vals):.0f}  (ms)")
