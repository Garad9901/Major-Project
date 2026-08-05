# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.db import models


class WebFetchLog(models.Model):
    """One row per fetch ATTEMPT, including the ones that were refused.

    Refusals matter more than successes here. A run of "refused: not on the
    allowlist" is the signal that something is trying to steer this component
    somewhere it should not go, and a log that only recorded successful fetches
    would show nothing at all while that happened.

    Separate from audit.AuditLog because the grain differs: one question can
    cause several fetches, or none, and a cache hit means content was used
    without any fetch happening.
    """

    OUTCOMES = [
        ("ok", "Fetched"),
        ("cached", "Served from cache"),
        ("refused", "Refused (not allowlisted / unsafe target)"),
        ("failed", "Fetch failed"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    url = models.TextField()
    # Blank when a URL was refused precisely because it matched no entry.
    allowlist_id = models.CharField(max_length=100, blank=True)
    outcome = models.CharField(max_length=10, choices=OUTCOMES, db_index=True)
    http_status = models.IntegerField(null=True, blank=True)
    bytes_returned = models.IntegerField(default=0)
    duration_ms = models.FloatField(default=0.0)
    # How many instruction-shaped lines were stripped before the model saw this.
    # Persistently non-zero for a given page is worth investigating.
    injection_lines_removed = models.IntegerField(default=0)
    detail = models.TextField(blank=True)
    # The question that triggered it, for correlating with the audit log.
    question = models.TextField(blank=True)

    class Meta:
        db_table = "web_fetch_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.outcome}: {self.url}"
