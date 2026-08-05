# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from sql_agent.service import ask

TEST_QUESTIONS = [
    "What courses does the Computer Science department offer?",
    "Which faculty members work in the Mathematics department?",
    "List all programs that take longer than 3 years to complete.",
    "What is the tuition fee for the Computer Science program?",
    "Show me the exam schedule for course CS310.",
]


class Command(BaseCommand):
    help = (
        "Runs 5 canned test questions through the SQL agent and prints the "
        "generated SQL for review. By default this ONLY generates and "
        "validates the SQL — it does not touch the database. Pass --execute "
        "to actually run the queries against rag_agent_ro and print results."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Also execute each generated query (as rag_agent_ro) and print the results.",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        mode = "GENERATE + EXECUTE" if execute else "GENERATE ONLY (dry run, no DB writes/reads of result data)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Mode: {mode}\n"))

        for i, question in enumerate(TEST_QUESTIONS, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{i}] Q: {question}"))
            result = ask(question, execute=execute)

            if result.error:
                self.stdout.write(self.style.ERROR(f"    REJECTED/ERROR: {result.error}"))
                if result.raw_llm_output:
                    self.stdout.write(f"    raw model output: {result.raw_llm_output!r}")
                self.stdout.write("")
                continue

            self.stdout.write(f"    SQL: {result.generated_sql}")

            if execute:
                self.stdout.write(f"    columns: {result.columns}")
                self.stdout.write(f"    row count: {len(result.rows)}")
                for row in result.rows[:5]:
                    self.stdout.write(f"      {row}")
                if len(result.rows) > 5:
                    self.stdout.write(f"      ... ({len(result.rows) - 5} more)")

            self.stdout.write("")
