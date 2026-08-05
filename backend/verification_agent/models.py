# Copyright (c) 2026 Yash Garad. All rights reserved.

import uuid

from django.db import models


class VerificationLog(models.Model):
    """One row per factual claim checked, not per question — this is what
    makes a claim-level hallucination catch-rate computable later, e.g.:

        SELECT action_taken, count(*) FROM verification_logs GROUP BY action_taken;

    Lives in the app-owner's database (not rag_agent_ro's schema) since this
    is internal audit data about the agents, not college data the RAG agent
    should ever read.
    """

    ACTION_CHOICES = [
        ("passed", "Passed"),
        ("corrected", "Corrected using source data"),
        ("flagged_unverifiable", "Flagged as unverifiable"),
    ]

    run_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    question = models.TextField()
    route = models.CharField(max_length=10)
    original_answer = models.TextField()
    final_answer = models.TextField()

    claim_text = models.TextField()
    supported = models.BooleanField()
    confidence = models.FloatField()
    evidence = models.TextField(blank=True)
    action_taken = models.CharField(max_length=25, choices=ACTION_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "verification_logs"

    def __str__(self):
        return f"[{self.action_taken}] {self.claim_text[:50]}"
