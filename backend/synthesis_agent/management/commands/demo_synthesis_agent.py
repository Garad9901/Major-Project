# Copyright (c) 2026 Yash Garad. All rights reserved.

from common.devonly import DevelopmentOnlyCommand

from rag_agent.service import retrieve
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer

# Routes are pre-assigned here (already validated by the router agent in an
# earlier step) so this command can focus on synthesis. Each case actually
# calls the live sql_agent/rag_agent — these are real outputs, not
# copy-pasted text from earlier runs. Includes one deliberately-empty SQL
# case (faculty/programs/etc. are unpopulated) to check the agent reports
# "no data" honestly instead of inventing an answer.
TEST_CASES = [
    {"question": "What courses does the Computer Science department offer?", "route": "SQL"},
    {"question": "Which faculty members work in the Mathematics department?", "route": "SQL"},
    {"question": "Tell me about the Computer Science department.", "route": "RAG"},
    {"question": "What does the Organic Chemistry course cover?", "route": "RAG"},
    {
        "question": "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
        "route": "BOTH",
    },
]


class Command(DevelopmentOnlyCommand):
    dev_only_reason = "it runs an agent against whatever database it is pointed at"

    help = (
        "Runs 5 test cases through the real SQL and/or RAG agents (per each "
        "case's route) and feeds their actual outputs into the synthesis "
        "agent, printing the upstream data and the final human-readable "
        "answer for review."
    )

    def handle(self, *args, **options):
        for i, case in enumerate(TEST_CASES, 1):
            question = case["question"]
            route = case["route"]
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{i}] Q: {question}  (route={route})"))

            sql_result = None
            rag_chunks = None

            if route in ("SQL", "BOTH"):
                sql_result = sql_ask(question, execute=True)
                self.stdout.write(f"    [sql_agent] SQL: {sql_result.generated_sql}")
                if sql_result.error:
                    self.stdout.write(self.style.WARNING(f"    [sql_agent] error: {sql_result.error}"))
                else:
                    self.stdout.write(f"    [sql_agent] rows ({len(sql_result.rows)}): {sql_result.rows}")

            if route in ("RAG", "BOTH"):
                rag_chunks = retrieve(question, top_k=3)
                for c in rag_chunks:
                    self.stdout.write(
                        f"    [rag_agent] [{c.table}#{c.row_id}] score={c.score:.3f} {c.text[:90]}"
                    )

            answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)
            self.stdout.write(self.style.SUCCESS(f"\n    FINAL ANSWER:\n    {answer}"))
