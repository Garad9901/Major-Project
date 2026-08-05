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
