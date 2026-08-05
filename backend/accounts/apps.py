# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Surfaces the production secret guard through `manage.py check`.
        # This is a convenience for operators and for the Phase 7 verification
        # script — it is NOT the enforcement mechanism. Enforcement happens at
        # settings-import time in config/settings/production.py, because
        # gunicorn loads config.wsgi directly and never runs system checks.
        from config.secret_guards import register_checks

        register_checks()
