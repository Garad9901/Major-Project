# Copyright (c) 2026 Yash Garad. All rights reserved.

from common.devonly import DevelopmentOnlyCommand

from rag_agent.service import retrieve

TEST_QUESTIONS = [
    "Tell me about the Computer Science department.",
    "What is the Mathematics department about?",
    "Which course covers neural networks and machine learning?",
    "I want to study Shakespeare's plays — which course should I take?",
    "What course teaches me about financial statements and accounting?",
]


class Command(DevelopmentOnlyCommand):
    dev_only_reason = "it runs an agent against whatever database it is pointed at"

    help = (
        "Runs 5 sample questions through the RAG retrieval agent (embed with "
        "nomic-embed-text, search Qdrant, top-k with source metadata) and "
        "prints the retrieved chunks so relevance can be checked by eye."
    )

    def add_arguments(self, parser):
        parser.add_argument("--top-k", type=int, default=5)

    def handle(self, *args, **options):
        top_k = options["top_k"]

        for i, question in enumerate(TEST_QUESTIONS, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{i}] Q: {question}"))
            chunks = retrieve(question, top_k=top_k)

            if not chunks:
                self.stdout.write(self.style.WARNING("    (no results — is the college_docs collection empty?)"))
                continue

            for rank, chunk in enumerate(chunks, 1):
                self.stdout.write(
                    f"    #{rank}  score={chunk.score:.4f}  "
                    f"[{chunk.table}#{chunk.row_id}]  {chunk.text}"
                )
