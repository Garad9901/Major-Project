# Copyright (c) 2026 Yash Garad. All rights reserved.

"""One control, tested once, covering every development-only command.

The point of DevelopmentOnlyCommand is that dangerous commands stop inventing
their own guards. mirror_to_mssql's first version checked whether MSSQL_HOST
looked like a college server — a guess about a string. seed_demo_data had a
separate requirement ("must be impossible to run against production") arriving
from a different direction. Three commands guarding themselves is three
heuristics of differing quality.

So the enumeration below is deliberately explicit rather than discovered by
scanning: a new dangerous command should have to be ADDED here, and the test
that every listed command actually carries the guard is what makes forgetting
visible.
"""

import os
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from common.devonly import DevelopmentOnlyCommand, is_production

# Commands that must never run against production, and the module each lives in.
DEV_ONLY_COMMANDS = [
    ("seed_demo_data", "academics.management.commands.seed_demo_data"),
    ("mirror_to_mssql", "academics.management.commands.mirror_to_mssql"),
    ("demo_rag_agent", "rag_agent.management.commands.demo_rag_agent"),
    ("demo_router_agent", "router_agent.management.commands.demo_router_agent"),
    ("demo_sql_agent", "sql_agent.management.commands.demo_sql_agent"),
    ("demo_synthesis_agent", "synthesis_agent.management.commands.demo_synthesis_agent"),
    ("demo_verification_agent", "verification_agent.management.commands.demo_verification_agent"),
]


class EveryDangerousCommandCarriesTheGuardTests(SimpleTestCase):
    def test_all_listed_commands_subclass_the_guard(self):
        import importlib

        for name, module_path in DEV_ONLY_COMMANDS:
            with self.subTest(command=name):
                module = importlib.import_module(module_path)
                self.assertTrue(
                    issubclass(module.Command, DevelopmentOnlyCommand),
                    f"{name} does not use DevelopmentOnlyCommand",
                )

    def test_each_states_what_it_would_do_to_production(self):
        # The default reason is generic. An operator who is blocked will go
        # looking for the way around the check, and a message that explains the
        # risk is what makes them stop instead.
        import importlib

        for name, module_path in DEV_ONLY_COMMANDS:
            with self.subTest(command=name):
                module = importlib.import_module(module_path)
                self.assertNotEqual(
                    module.Command.dev_only_reason,
                    DevelopmentOnlyCommand.dev_only_reason,
                    f"{name} left dev_only_reason at the default",
                )


class TheGuardRefusesUnderProductionTests(SimpleTestCase):
    def test_is_production_reads_the_authoritative_variable(self):
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            self.assertTrue(is_production())
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "development"}):
            self.assertFalse(is_production())
        # Absent defaults to development, matching config/settings/__init__.py.
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_ENV"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_production())

    def test_a_dev_only_command_refuses_under_production(self):
        # seed_demo_data is used as the representative because it is the one
        # with a standing instruction that it must not reach production.
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError) as caught:
                call_command("seed_demo_data")
        self.assertIn("DEVELOPMENT-ONLY", str(caught.exception))

    def test_the_check_cannot_be_skipped_by_a_subclass_overriding_handle(self):
        # The guard runs in execute(), not handle(), precisely so a subclass
        # that forgets to call super().handle() still cannot run.
        class Sneaky(DevelopmentOnlyCommand):
            dev_only_reason = "test"

            def handle(self, *args, **options):
                return "should never be reached"

        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}):
            with self.assertRaises(CommandError):
                Sneaky().execute(verbosity=0, no_color=True, force_color=False)
