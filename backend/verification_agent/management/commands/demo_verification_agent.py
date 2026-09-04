# Copyright (c) 2026 Yash Garad. All rights reserved.

from common.devonly import DevelopmentOnlyCommand
from django.db.models import Count

from rag_agent.service import retrieve
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer
from verification_agent.models import VerificationLog
from verification_agent.service import verify_and_correct

BASE_CASES = [
    {"question": "What courses does the Computer Science department offer?", "route": "SQL"},
    {"question": "Which faculty members work in the Mathematics department?", "route": "SQL"},
    {"question": "Tell me about the Computer Science department.", "route": "RAG"},
    {"question": "What does the Organic Chemistry course cover?", "route": "RAG"},
    {
        "question": "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
        "route": "BOTH",
    },
]

# Deliberately fabricated sentences spliced onto a genuine synthesis answer —
# none of this is anywhere in the SQL rows or RAG passages backing each
# case. This is the actual test of whether the verifier catches information
# the synthesis agent (or here, a stand-in for it) added out of nowhere,
# rather than just checking it agrees with itself.
INJECTED_HALLUCINATIONS = [
    " The department also has 12 full-time faculty members specializing in AI research.",
    " The department head is Dr. Jane Smith, who has led the department since 2015.",
    " The department was ranked #1 nationally for computer science education in 2020.",
    " Enrollment is capped at 30 students per semester, with a waiting list typically forming by the second week.",
    " The course is taught by Professor John Doe and maintains an average student rating of 4.8 out of 5.",
]


class Command(DevelopmentOnlyCommand):
    dev_only_reason = "it runs an agent against whatever database it is pointed at"

    help = (
        "Runs 10 test cases through the verification agent: 5 genuine "
        "synthesis answers (checking for false positives) and the same 5 "
        "with a fabricated sentence spliced in (checking the hallucination "
        "catch rate). Every claim check is logged to verification_logs."
    )

    def handle(self, *args, **options):
        run_ids = []
        injected_caught = 0
        genuine_false_positives = 0

        for i, case in enumerate(BASE_CASES, 1):
            question = case["question"]
            route = case["route"]

            sql_result = sql_ask(question, execute=True) if route in ("SQL", "BOTH") else None
            rag_chunks = retrieve(question, top_k=3) if route in ("RAG", "BOTH") else None
            genuine_answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)

            r1 = self._run_case(i, question, route, genuine_answer, sql_result, rag_chunks, injected=False)
            run_ids.append(r1.run_id)
            if any(not c["supported"] for c in r1.claims):
                genuine_false_positives += 1

            hallucinated_answer = genuine_answer + INJECTED_HALLUCINATIONS[i - 1]
            r2 = self._run_case(i + 5, question, route, hallucinated_answer, sql_result, rag_chunks, injected=True)
            run_ids.append(r2.run_id)
            if any(not c["supported"] for c in r2.claims):
                injected_caught += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary ==="))
        self.stdout.write(f"  Injected hallucinations caught: {injected_caught}/5")
        self.stdout.write(f"  Genuine answers with a false-positive flag: {genuine_false_positives}/5")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== verification_logs tally for this run (real DB query) ==="))
        tally = VerificationLog.objects.filter(run_id__in=run_ids).values("action_taken").annotate(count=Count("id"))
        for row in tally:
            self.stdout.write(f"  {row['action_taken']}: {row['count']}")
        total_claims = VerificationLog.objects.filter(run_id__in=run_ids).count()
        self.stdout.write(f"  total claims logged: {total_claims}")

    def _run_case(self, idx, question, route, answer, sql_result, rag_chunks, injected):
        label = "INJECTED HALLUCINATION" if injected else "genuine"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{idx}] ({label}) Q: {question}"))
        self.stdout.write(f"    answer under test: {answer}")

        result = verify_and_correct(question, route, answer, sql_result=sql_result, rag_chunks=rag_chunks)

        for claim in result.claims:
            verdict = "PASS" if claim["supported"] else "FLAGGED"
            style = self.style.SUCCESS if claim["supported"] else self.style.ERROR
            self.stdout.write(style(f"    [{verdict}] conf={claim['confidence']:.2f}  \"{claim['text']}\""))
            self.stdout.write(f"        evidence: {claim['evidence']}")

        if result.was_corrected:
            self.stdout.write(self.style.WARNING(f"    CORRECTED FINAL ANSWER: {result.final_answer}"))
        else:
            self.stdout.write("    (no correction needed)")

        return result
