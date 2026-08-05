# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class WebAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web_agent"

    def ready(self):
        # Validate the allowlist at startup rather than on the first question.
        # A malformed file should stop the container, not surface as a confusing
        # "no results" much later.
        from . import allowlist
        allowlist.load(force=True)
