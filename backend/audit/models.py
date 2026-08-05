# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.db import models


class AuditLog(models.Model):
    """One row per question asked through /api/ask/ — who asked, which agent(s)
    handled it, the exact SQL run (if any), and the final answer. Separate from
    verification_logs (which is claim-level fact-checking); this is
    request-level accountability for a system sitting over institutional data.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    username = models.CharField(max_length=150, db_index=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)

    question = models.TextField()  # already sanitized before storage
    route = models.CharField(max_length=10, blank=True)  # SQL / RAG / BOTH
    agents_used = models.CharField(max_length=20, blank=True)
    generated_sql = models.TextField(null=True, blank=True)
    final_answer = models.TextField(blank=True)
    injection_flags = models.TextField(blank=True)  # sanitizer flags, if any
    latency_ms = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.username}: {self.question[:50]}"
