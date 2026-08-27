# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The model puller and the readiness check must never disagree.

THE DEFECT THIS EXISTS TO PREVENT
ollama-pull looped over a hand-written list of three environment variables
while the application read six. ROUTER_MODEL was missing, and it has its OWN
default (qwen2.5:3b) rather than falling back to LLM_MODEL — so on a default
deployment a model the router needs was never downloaded, while
common.ollama._configured_models() counted it as required-resident.
/api/health/ then reports "loading qwen2.5:3b" and returns 503 FOREVER,
because nothing will ever fetch it.

It went unnoticed because VERIFICATION_MODEL happened to be set to the same
value ROUTER_MODEL defaults to. Measured with the compose file's exact
enumeration:

    VERIFICATION_MODEL=qwen2.5:3b   -> nomic-embed-text qwen2.5:7b qwen2.5:3b
    VERIFICATION_MODEL=<blank>      -> nomic-embed-text qwen2.5:7b
    VERIFICATION_MODEL=llama3.2:1b  -> nomic-embed-text qwen2.5:7b llama3.2:1b

and the consequence, measured against the live server with a model the puller
would never fetch:

    is_ready([..., 'mistral:7b'])   ->   (False, 'loading mistral:7b')

These tests run the ACTUAL shell script ollama-pull executes and compare it
against the ACTUAL function the health check calls, so the two cannot drift
apart again without failing the suite. No Ollama server is involved.

WHY THE SCRIPT LIVES UNDER backend/
It is a deployment script and would naturally sit in the repository's top-level
scripts/ directory. It cannot: the backend image's build context is ./backend,
and the test container mounts only that, so a script at the repository root is
unreachable from here — and a comparison test that cannot read one side of the
comparison is a test that quietly checks nothing. docker-compose.yml bind-mounts
it into ollama-pull from this location.
"""

import os
import subprocess
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase

from common import ollama

SCRIPT = Path(settings.BASE_DIR) / "scripts" / "required_models.sh"


class RequiredModelsMatchesReadinessTests(SimpleTestCase):
    def _shell(self, env, chat_only=False):
        """What ollama-pull would fetch, from the real script."""
        self.assertTrue(
            SCRIPT.is_file(),
            f"{SCRIPT} is missing — ollama-pull's model list has no source of "
            f"truth and this test is checking nothing",
        )
        argv = ["sh", str(SCRIPT)] + (["--chat"] if chat_only else [])
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            # A clean environment: the test runner's own model variables must
            # not leak in and make a failing case look like it passes.
            env={"PATH": os.environ.get("PATH", "/bin:/usr/bin"), **env},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _python(self, env):
        """What the readiness check requires to be resident."""
        with mock.patch.dict(os.environ, env, clear=True):
            return ollama._configured_models()

    def _assert_agree(self, env, label):
        shell = self._shell(env)
        python = self._python(env)
        self.assertEqual(
            sorted(shell), sorted(python),
            f"{label}: ollama-pull would fetch {shell} but readiness requires "
            f"{python}. A model in the second list and not the first makes "
            f"/api/health/ report 'loading' forever.",
        )
        return shell

    # -- the case that was actually broken -------------------------------------

    def test_router_model_is_fetched_when_verification_is_blank(self):
        """The exact reproduction: .env.production tells operators blank is fine."""
        models = self._assert_agree(
            {"EMBEDDING_MODEL": "nomic-embed-text",
             "LLM_MODEL": "qwen2.5:7b",
             "VERIFICATION_MODEL": ""},
            "VERIFICATION_MODEL blank",
        )
        self.assertIn("qwen2.5:3b", models, "the router's model is not being fetched")

    def test_router_model_is_fetched_when_verification_is_a_different_model(self):
        models = self._assert_agree(
            {"EMBEDDING_MODEL": "nomic-embed-text",
             "LLM_MODEL": "qwen2.5:7b",
             "VERIFICATION_MODEL": "llama3.2:1b"},
            "VERIFICATION_MODEL distinct",
        )
        self.assertIn("qwen2.5:3b", models)
        self.assertIn("llama3.2:1b", models)

    def test_router_model_is_fetched_on_a_bare_default_deployment(self):
        """Nothing set at all, which is what a fresh install looks like."""
        models = self._assert_agree({}, "all defaults")
        for expected in ("nomic-embed-text", "qwen2.5:7b", "qwen2.5:3b"):
            self.assertIn(expected, models)

    # -- the other overrides that were also missing ----------------------------

    def test_synthesis_model_is_fetched_when_set_independently(self):
        models = self._assert_agree(
            {"LLM_MODEL": "qwen2.5:7b", "SYNTHESIS_MODEL": "mistral:7b"},
            "SYNTHESIS_MODEL distinct",
        )
        self.assertIn("mistral:7b", models)

    def test_sql_agent_model_is_fetched_when_set_independently(self):
        """Absent from _configured_models() entirely before this change."""
        models = self._assert_agree(
            {"LLM_MODEL": "qwen2.5:7b", "SQL_AGENT_MODEL": "codellama:7b"},
            "SQL_AGENT_MODEL distinct",
        )
        self.assertIn("codellama:7b", models)

    def test_six_distinct_models_are_all_fetched(self):
        env = {
            "EMBEDDING_MODEL": "emb:1", "LLM_MODEL": "llm:1",
            "ROUTER_MODEL": "router:1", "VERIFICATION_MODEL": "verify:1",
            "SYNTHESIS_MODEL": "synth:1", "SQL_AGENT_MODEL": "sql:1",
        }
        models = self._assert_agree(env, "six distinct")
        for expected in ("emb:1", "llm:1", "router:1", "verify:1", "synth:1", "sql:1"):
            self.assertIn(expected, models)

    # -- properties of the list itself -----------------------------------------

    def test_models_are_deduplicated(self):
        """The normal case: every override resolving to LLM_MODEL.

        A duplicate is merely wasteful when pulling, but the residency check
        reports each entry separately, so it would read as two problems.
        """
        models = self._assert_agree(
            {"LLM_MODEL": "qwen2.5:7b", "VERIFICATION_MODEL": "qwen2.5:7b",
             "SYNTHESIS_MODEL": "qwen2.5:7b", "SQL_AGENT_MODEL": "qwen2.5:7b"},
            "all overrides equal to LLM_MODEL",
        )
        self.assertEqual(len(models), len(set(models)))

    def test_no_blank_entries_are_emitted(self):
        models = self._assert_agree(
            {"LLM_MODEL": "qwen2.5:7b", "VERIFICATION_MODEL": "",
             "SYNTHESIS_MODEL": "", "SQL_AGENT_MODEL": "", "ROUTER_MODEL": ""},
            "every override blank",
        )
        self.assertNotIn("", models)
        self.assertTrue(all(m.strip() for m in models))

    def test_chat_mode_excludes_embedding_models(self):
        """--chat drives the preload and the residency check.

        An embedding model never receives a chat request, so it never appears in
        `ollama ps`. Including it would report a healthy system as incomplete.
        """
        chat = self._shell(
            {"EMBEDDING_MODEL": "nomic-embed-text", "LLM_MODEL": "qwen2.5:7b"},
            chat_only=True,
        )
        self.assertNotIn("nomic-embed-text", chat)
        self.assertIn("qwen2.5:7b", chat)


class BlankModelVariablesFallBackTests(SimpleTestCase):
    """A blank override has to mean what the documentation says it means.

    os.getenv(name, default) applies the default only when the name is ABSENT;
    a variable that is set but empty returns "". Every per-agent override was
    written that way, while .env.production says of VERIFICATION_MODEL:

        "Leave this blank to use LLM_MODEL for verification too"

    Following that instruction produced an EMPTY model name. Verified before
    the fix: VERIFICATION_MODEL= resolved to '' rather than qwen2.5:7b.
    """

    def test_blank_resolves_to_the_fallback(self):
        with mock.patch.dict(os.environ, {"VERIFICATION_MODEL": ""}, clear=True):
            self.assertEqual(
                ollama.model_from_env("VERIFICATION_MODEL", "qwen2.5:7b"), "qwen2.5:7b")

    def test_whitespace_only_resolves_to_the_fallback(self):
        with mock.patch.dict(os.environ, {"VERIFICATION_MODEL": "   "}, clear=True):
            self.assertEqual(
                ollama.model_from_env("VERIFICATION_MODEL", "qwen2.5:7b"), "qwen2.5:7b")

    def test_unset_resolves_to_the_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                ollama.model_from_env("VERIFICATION_MODEL", "qwen2.5:7b"), "qwen2.5:7b")

    def test_a_real_value_wins(self):
        with mock.patch.dict(os.environ, {"VERIFICATION_MODEL": "qwen2.5:3b"}, clear=True):
            self.assertEqual(
                ollama.model_from_env("VERIFICATION_MODEL", "qwen2.5:7b"), "qwen2.5:3b")
