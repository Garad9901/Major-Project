# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Guards on the one file a college fills in.

The properties worth pinning down here are not "does JSON parse". They are:

  * a broken config must not lock everyone out of a working system
  * a fresh install must not be able to claim an institution name it was never
    given
  * the unauthenticated endpoint must publish an ALLOWLIST, so a field added to
    institution.json later is not accidentally exposed to the internet
"""

import json
import os
import tempfile
from unittest import mock

from django.test import SimpleTestCase
from django.urls import reverse

from institution import config


class _TempConfig:
    """Point config.CONFIG_PATH at a temporary file for one test."""

    def __init__(self, payload, raw=None):
        self.payload = payload
        self.raw = raw

    def __enter__(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        handle.write(self.raw if self.raw is not None else json.dumps(self.payload))
        handle.close()
        self.path = handle.name
        self._patch = mock.patch.object(config, "CONFIG_PATH", self.path)
        self._patch.start()
        config.get(refresh=True)
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        os.unlink(self.path)
        config.get(refresh=True)
        return False


class DefaultsNameNobodyTests(SimpleTestCase):
    """A fresh install must not ship claiming to be some institution."""

    def test_default_name_is_empty(self):
        self.assertEqual(config.DEFAULTS["institution"]["name"], "")

    def test_missing_file_is_not_configured(self):
        with mock.patch.object(config, "CONFIG_PATH", "/nonexistent/institution.json"):
            config.get(refresh=True)
            self.assertFalse(config.is_configured())
            self.assertTrue(any("No institution config" in p for p in config.problems()))
        config.get(refresh=True)

    def test_a_blank_name_counts_as_unconfigured(self):
        """Whitespace is not a name. Someone will type a space to get past setup."""
        with _TempConfig({"institution": {"name": "   "}}):
            self.assertFalse(config.is_configured())

    def test_a_real_name_configures_it(self):
        with _TempConfig({"institution": {"name": "Riverside Institute of Technology"}}):
            self.assertTrue(config.is_configured())
            self.assertEqual(config.problems(), [])


class BrokenConfigDoesNotLockAnyoneOutTests(SimpleTestCase):
    """The sign-in screen reads this endpoint, so a bad file must degrade rather
    than fail. An operator typo must not be an outage."""

    def test_malformed_json_falls_back_to_defaults(self):
        with _TempConfig(None, raw="{ this is not json"):
            served = config.public()
            self.assertEqual(served["institution"]["descriptor"], "Academic Information Service")
            self.assertFalse(served["configured"])

    def test_malformed_json_reports_line_and_column(self):
        """'Invalid JSON' alone sends an operator hunting through 150 lines."""
        with _TempConfig(None, raw='{\n  "institution": {\n    "name": "X",,\n  }\n}'):
            joined = " ".join(config.problems())
            self.assertIn("line", joined)
            self.assertIn("column", joined)

    def test_a_json_array_is_rejected_not_crashed_on(self):
        with _TempConfig(None, raw='["not", "an", "object"]'):
            self.assertFalse(config.is_configured())
            self.assertTrue(any("top level" in p for p in config.problems()))


class PartialConfigMergesTests(SimpleTestCase):
    """An operator setting only the name must not have to restate the theme, and
    a file written before a field existed must survive the upgrade that adds
    it."""

    def test_unspecified_fields_keep_their_defaults(self):
        with _TempConfig({"institution": {"name": "Riverside"}}):
            served = config.public()
            self.assertEqual(served["institution"]["footnote"], "Authorised users only")
            self.assertEqual(served["theme"]["accent"], config.DEFAULTS["theme"]["accent"])

    def test_a_single_theme_colour_can_be_overridden_alone(self):
        with _TempConfig({"institution": {"name": "R"}, "theme": {"accent": "#ff0000"}}):
            served = config.public()
            self.assertEqual(served["theme"]["accent"], "#ff0000")
            self.assertEqual(served["theme"]["identity_ink"],
                             config.DEFAULTS["theme"]["identity_ink"])

    def test_short_name_falls_back_to_name(self):
        with _TempConfig({"institution": {"name": "Riverside Institute of Technology"}}):
            self.assertEqual(config.public()["institution"]["short_name"],
                             "Riverside Institute of Technology")


class TheEndpointPublishesAnAllowlistTests(SimpleTestCase):
    """public() is an allowlist, not a blocklist. This is the test that stops a
    future field from being published to unauthenticated callers by default."""

    def test_an_unknown_field_is_not_served(self):
        with _TempConfig({
            "institution": {"name": "Riverside", "smtp_password": "hunter2"},
            "internal_notes": "do not publish",
        }):
            served = json.dumps(config.public())
            self.assertNotIn("hunter2", served)
            self.assertNotIn("smtp_password", served)
            self.assertNotIn("internal_notes", served)

    def test_web_sources_are_never_served(self):
        """Not secret, but an inventory of what the fetcher can reach is not
        something to hand an unauthenticated client."""
        with _TempConfig({
            "institution": {"name": "Riverside"},
            "web_sources": {"urls": [{"id": "x", "url": "https://internal.example.edu/",
                                      "label": "Internal", "topics": ["x"]}]},
        }):
            self.assertNotIn("internal.example.edu", json.dumps(config.public()))

    def test_documentation_keys_are_stripped(self):
        with _TempConfig({
            "_README": ["a long explanation"],
            "institution": {"name": "Riverside", "_field_notes": {"name": "the full name"}},
        }):
            served = json.dumps(config.public())
            self.assertNotIn("_README", served)
            self.assertNotIn("_field_notes", served)


class EndpointIsReachableWithoutSigningInTests(SimpleTestCase):
    """The sign-in screen renders before anyone has a session."""

    def test_anonymous_get_succeeds(self):
        response = self.client.get(reverse("institution"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("institution", response.json())
        self.assertIn("configured", response.json())
