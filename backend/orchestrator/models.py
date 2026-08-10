# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Chat history: conversations and the messages inside them.

WHY THIS IS NOT THE AUDIT LOG
audit.AuditLog already records every question and answer, so it looks like it
could back the sidebar. It must not. The two have opposite requirements:

  audit log      a compliance record. Append-only, covers EVERY user, purged on
                 a fixed retention schedule (AUDIT_LOG_RETENTION_DAYS), and read
                 by whoever is responsible for oversight.
  chat history   a convenience feature. Owned by one user, who reasonably
                 expects to delete a conversation — and deleting it must NOT
                 erase the audit trail.

Backing the UI with the audit log would mean either letting users delete audit
records, or purging their chat history after 90 days because a governance
setting said so. Both are wrong, so these are separate tables.
"""

from django.contrib.auth.models import User
from django.db import models


def title_from(text, limit=60):
    """A conversation title derived from its first message.

    Collapses whitespace (a pasted multi-line question would otherwise produce a
    title with newlines in it) and cuts on a word boundary so titles do not end
    mid-word.
    """
    clean = " ".join((text or "").split())
    if not clean:
        return "New chat"
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0]
    return (cut or clean[:limit]) + "…"


class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=120, default="New chat")
    created_at = models.DateTimeField(auto_now_add=True)
    # Ordering key for the sidebar. Bumped on every new message so an active
    # conversation rises to the top; `created_at` alone would freeze the order.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversation"
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class Message(models.Model):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant")]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    # Which agent path answered. Rendered as a small badge in the UI, and null
    # for user messages.
    route = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_message"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"{self.role}: {self.text[:40]}"


class QueryProfile(models.Model):
    """Per-stage latency for one answered question.

    WHY THIS IS A TABLE AND NOT JUST A LOG LINE
    orchestrator/profiling.py has logged a PROFILE line per question for a
    while. That is enough to inspect one request and useless for the question
    that actually matters — "where does the time go across the last hundred
    real questions?" — because answering it from logs means the logs must still
    exist, must not have rotated, must cover a representative period, and must
    be parsed with a regex that breaks whenever the log line changes.

    A row per question makes the p50/p95/p99 a query. It also means the data
    survives a container restart, which the previous approach did not: the
    profile rode along on the SSE `done` event and was then discarded, so every
    latency claim had to be backed by a fresh benchmark run rather than by what
    users had actually experienced.

    WHY NOT EXTEND AuditLog
    AuditLog already stores `latency_ms` and it was tempting to add six more
    columns there. It is a compliance record with its own retention rule
    (AUDIT_LOG_RETENTION_DAYS), and performance data has neither the same
    sensitivity nor the same lifetime — it holds no answer text and can be
    truncated freely. Same reasoning as Conversation vs AuditLog above.

    THE DENORMALISED COLUMNS ARE DELIBERATE
    `stages` holds the full profile as JSON and is the source of truth. The
    individual *_ms columns duplicate values already inside it, so that the
    common aggregations are plain SQL rather than a JSON traversal per row.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    question = models.TextField()
    route = models.CharField(max_length=10, blank=True)

    # Wall time inside the pipeline generator, i.e. what profiling.Profile
    # measured. NOT the same as AuditLog.latency_ms, which is measured in the
    # view and so also covers request parsing and the audit write itself.
    total_ms = models.FloatField()
    # Request start to the first answer token reaching the client. The number
    # the "first token within 1-2 seconds" target is judged against.
    ttft_ms = models.FloatField(null=True, blank=True)

    router_ms = models.FloatField(null=True, blank=True)
    sql_ms = models.FloatField(null=True, blank=True)
    rag_ms = models.FloatField(null=True, blank=True)
    web_ms = models.FloatField(null=True, blank=True)
    synthesis_ms = models.FloatField(null=True, blank=True)
    verification_ms = models.FloatField(null=True, blank=True)
    # Time not attributable to any named stage: slot wait, cache lookup,
    # serialisation, SSE writes. See Profile.overhead_ms.
    overhead_ms = models.FloatField(null=True, blank=True)

    # Ollama's own split, summed over every call the question made. These are
    # what distinguish "slow because it read a lot" from "slow because it wrote
    # a lot", which have completely different fixes.
    prompt_tokens = models.IntegerField(null=True, blank=True)
    prompt_ms = models.FloatField(null=True, blank=True)
    gen_tokens = models.IntegerField(null=True, blank=True)
    gen_ms = models.FloatField(null=True, blank=True)

    # Which verification tier settled it: "fast" (no LLM) or "llm". Recorded so
    # the claim that verification was moved off the LLM can be checked against
    # real traffic rather than against the code.
    verification_tier = models.CharField(max_length=10, blank=True)
    # "exact", "semantic", "coalesced", or blank for a generated answer.
    cached = models.CharField(max_length=16, blank=True)

    stages = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "query_profile"
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"[{self.route}] {self.total_ms:.0f}ms {self.question[:40]}"
