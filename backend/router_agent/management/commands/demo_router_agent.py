# Copyright (c) 2026 Yash Garad. All rights reserved.

from common.devonly import DevelopmentOnlyCommand

from router_agent.classifier import classify

# Mix of clear SQL lookups, clear RAG/descriptive questions, and a few that
# genuinely need both, to exercise all three routes before wiring this into
# anything else.
TEST_QUESTIONS = [
    "How many faculty members work in the Computer Science department?",
    "What does the Organic Chemistry course cover?",
    "List all programs offered by the Mathematics department.",
    "Tell me about the Computer Science department.",
    "What is the tuition fee for the Computer Science program?",
    "When is the exam scheduled for course CS310?",
    "I'm interested in studying literature — what courses would you recommend and when are they scheduled?",
    "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
    "Which department was established in 1970?",
    "Describe the Financial Accounting course and tell me its exam date.",
]


class Command(DevelopmentOnlyCommand):
    dev_only_reason = "it runs an agent against whatever database it is pointed at"

    help = (
        "Classifies 10 mixed test questions as SQL / RAG / BOTH using the "
        "router agent and prints each classification + reasoning for "
        "review. This is classification only — it does not call the SQL "
        "or RAG agents themselves."
    )

    def handle(self, *args, **options):
        counts = {"SQL": 0, "RAG": 0, "BOTH": 0, "ERROR": 0}

        for i, question in enumerate(TEST_QUESTIONS, 1):
            result = classify(question)
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{i}] Q: {question}"))

            if result.error:
                counts["ERROR"] += 1
                self.stdout.write(self.style.ERROR(f"    ERROR: {result.error}"))
                if result.raw_output:
                    self.stdout.write(f"    raw output: {result.raw_output!r}")
            else:
                counts[result.route] += 1
                self.stdout.write(f"    ROUTE: {result.route}  —  {result.reason}")

            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("Summary:"))
        self.stdout.write(
            f"  SQL={counts['SQL']}  RAG={counts['RAG']}  BOTH={counts['BOTH']}  ERROR={counts['ERROR']}"
        )
