# Copyright (c) 2026 Yash Garad. All rights reserved.

from unittest import mock

from django.test import SimpleTestCase

from common import ollama
from health import views as health_views


class WarmingIsNotReadyTests(SimpleTestCase):
    """A fresh deployment reported itself healthy for the ~15 minutes it spent
    loading models, while every question timed out.

    ollama.ping() GETs /api/tags — the models on DISK — which answers 200 as
    soon as the server is listening. Demonstrated against the live stack: with
    all three models explicitly unloaded, /api/health/ still returned
    {"status":"ok","llm":"up"} with HTTP 200.
    """

    def test_ping_still_only_means_reachable(self):
        """Not a regression guard on ping so much as a statement of its scope:
        it must NOT be taught to imply readiness, because other callers want
        pure liveness."""
        with mock.patch.object(ollama.requests, "get") as get:
            get.return_value = mock.Mock(status_code=200)
            self.assertTrue(ollama.ping())
            self.assertIn("/api/tags", get.call_args[0][0])

    def _ps(self, names):
        resp = mock.Mock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"models": [{"name": n} for n in names]}
        return resp

    def test_no_models_resident_is_not_ready(self):
        with mock.patch.object(ollama.requests, "get", return_value=self._ps([])):
            ready, detail = ollama.is_ready(models=["qwen2.5:7b"])
        self.assertFalse(ready)
        self.assertIn("loading", detail)

    def test_the_configured_model_resident_is_ready(self):
        with mock.patch.object(ollama.requests, "get",
                               return_value=self._ps(["qwen2.5:7b"])):
            ready, _ = ollama.is_ready(models=["qwen2.5:7b"])
        self.assertTrue(ready)

    def test_a_different_model_resident_is_not_ready(self):
        """Loading the 3B does not make a 7B question fast."""
        with mock.patch.object(ollama.requests, "get",
                               return_value=self._ps(["qwen2.5:3b"])):
            ready, detail = ollama.is_ready(models=["qwen2.5:7b"])
        self.assertFalse(ready)
        self.assertIn("qwen2.5:7b", detail)

    def test_latest_tag_is_tolerated(self):
        """/api/ps reports nomic-embed-text:latest for a model configured as
        nomic-embed-text. That must not read as perpetually warming."""
        with mock.patch.object(ollama.requests, "get",
                               return_value=self._ps(["nomic-embed-text:latest"])):
            ready, _ = ollama.is_ready(models=["nomic-embed-text"])
        self.assertTrue(ready)

    def test_unreachable_is_distinguished_from_warming(self):
        """down and warming need different operator responses: one is restart
        the container, the other is wait."""
        import requests as _rq
        with mock.patch.object(ollama.requests, "get",
                               side_effect=_rq.RequestException("refused")):
            self.assertIsNone(ollama.loaded_models())
            ready, detail = ollama.is_ready(models=["qwen2.5:7b"])
        self.assertFalse(ready)
        self.assertIn("not reachable", detail)

    def test_partial_residency_is_still_warming(self):
        """Every model a question can reach must be resident. One missing means
        some questions cold-load."""
        with mock.patch.object(ollama.requests, "get",
                               return_value=self._ps(["qwen2.5:7b"])):
            ready, detail = ollama.is_ready(models=["qwen2.5:7b", "qwen2.5:3b"])
        self.assertFalse(ready)
        self.assertIn("qwen2.5:3b", detail)


class HealthReportsWarmingAsNotReadyTests(SimpleTestCase):
    """The endpoint a load balancer consults must not say 200 while warming."""

    def _health(self, ready, reachable=True):
        with mock.patch.object(health_views.ollama, "is_ready",
                               return_value=(ready, "loading qwen2.5:7b")), \
             mock.patch.object(health_views.ollama, "ping", return_value=reachable), \
             mock.patch.object(health_views, "_check_database", return_value=True), \
             mock.patch.object(health_views, "_check_sessions", return_value=True), \
             mock.patch.object(health_views, "_check_vector_store", return_value=True):
            return self.client.get("/api/health/")

    def test_warming_returns_503_not_200(self):
        response = self._health(ready=False, reachable=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["services"]["llm"], "warming")

    def test_warming_is_reported_distinctly_from_down(self):
        self.assertEqual(self._health(False, reachable=True).json()["services"]["llm"],
                         "warming")
        self.assertEqual(self._health(False, reachable=False).json()["services"]["llm"],
                         "down")

    def test_ready_returns_200(self):
        response = self._health(ready=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["services"]["llm"], "up")
        self.assertEqual(response.json()["status"], "ok")

    def test_warming_explains_itself(self):
        """An operator seeing 503 needs to know whether to wait or to act."""
        self.assertIn("loading", self._health(ready=False).json()["llm_detail"])
