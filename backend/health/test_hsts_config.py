# Copyright (c) 2026 Yash Garad. All rights reserved.

"""The two HSTS knobs must never disagree.

THE DEFECT THIS EXISTS TO PREVENT
HSTS is set in two places and only one of them reaches a browser:

    Caddyfile.prod   Strict-Transport-Security "max-age={$CADDY_HSTS_MAX_AGE:0}"
    production.py    SECURE_HSTS_SECONDS = DJANGO_HSTS_SECONDS

Caddy terminates TLS in front of Django and a Caddy header directive REPLACES
rather than appends, so the browser only ever receives CADDY_HSTS_MAX_AGE.

Every operator document once named DJANGO_HSTS_SECONDS as the knob to ramp, and
CADDY_HSTS_MAX_AGE appeared in no document and in no env file at all. An operator
following DEPLOYMENT.md Step 8 would therefore set DJANGO_HSTS_SECONDS to a year,
restart, and believe the site was pinned — while Caddy went on stamping
`max-age=0` over it, which does not merely leave HSTS off but instructs browsers
to DISCARD a pin they already hold. Documented-as-protected while actually
unprotected is the failure this project treats as its worst kind, so the drift is
pinned mechanically here rather than left to review.

This asserts the two values move TOGETHER. It does not assert either is enabled:
off is the correct and deliberate default until the certificate is confirmed.
"""

import os
import re

from django.test import SimpleTestCase

_ENV_PRODUCTION = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".env.production",
)


def _read(path):
    """name -> value for a dotenv-style file. Values are not secrets here; only
    the two HSTS knobs are ever read out of the result."""
    values = {}
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Z_0-9]+)=(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return values


class HstsKnobsAgreeTests(SimpleTestCase):
    """Skips when .env.production is absent, so a dev checkout still runs green."""

    def setUp(self):
        if not os.path.exists(_ENV_PRODUCTION):
            self.skipTest("no .env.production on this machine")
        self.env = _read(_ENV_PRODUCTION)

    def test_the_caddy_knob_is_present(self):
        """Absent is how this went wrong: it existed only as a compose default."""
        self.assertIn(
            "CADDY_HSTS_MAX_AGE", self.env,
            "CADDY_HSTS_MAX_AGE is missing from .env.production. It is the value "
            "the browser actually receives; leaving it to the compose default "
            "means the documented ramp silently does nothing.",
        )

    def test_the_django_knob_is_present(self):
        self.assertIn("DJANGO_HSTS_SECONDS", self.env)

    def test_the_two_knobs_carry_the_same_value(self):
        caddy = self.env.get("CADDY_HSTS_MAX_AGE", "")
        django = self.env.get("DJANGO_HSTS_SECONDS", "")
        self.assertEqual(
            caddy, django,
            "HSTS knobs disagree: CADDY_HSTS_MAX_AGE=%r but DJANGO_HSTS_SECONDS=%r. "
            "Caddy's is what a browser sees. Ramp both together, or the one that "
            "counts stays where it was." % (caddy, django),
        )

    def test_both_are_whole_numbers_of_seconds(self):
        """A blank or non-numeric value renders as max-age= and is ignored."""
        for name in ("CADDY_HSTS_MAX_AGE", "DJANGO_HSTS_SECONDS"):
            with self.subTest(name=name):
                value = self.env.get(name, "")
                self.assertRegex(
                    value, r"^\d+$",
                    f"{name}={value!r} is not a whole number of seconds.",
                )
