# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Guards on the staff-only admin endpoints.

THE ACCESS TESTS ARE THE IMPORTANT ONES. The allowlist endpoint decides what
URLs this server will fetch. If a non-staff user can write to it, they can point
the fetcher at anything reachable from the server — an SSRF primitive handed out
through an admin panel. Every route is checked anonymous, as a normal user, and
as staff.

The write tests cover the failure that would make the panel a liability rather
than a feature: a bad save destroying a working configuration.
"""

import json
import os
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from institution import config, writer

User = get_user_model()

ROUTES = [
    ("admin-allowlist", "get"),
    ("admin-identity", "get"),
    ("admin-users", "get"),
    ("admin-settings", "get"),
]


class _TempConfig:
    """Point the config at a temp file so tests never touch the real one."""

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(self.payload, handle)
        handle.close()
        self.path = handle.name
        self._patch = mock.patch.object(config, "CONFIG_PATH", self.path)
        self._patch.start()
        config.get(refresh=True)
        return self

    def read(self):
        with open(self.path, encoding="utf-8") as handle:
            return json.load(handle)

    def __exit__(self, *exc):
        self._patch.stop()
        for path in (self.path, self.path + ".bak"):
            if os.path.exists(path):
                os.unlink(path)
        config.get(refresh=True)
        return False


class OnlyStaffCanReachTheseTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", password="x", is_staff=True)
        self.normal = User.objects.create_user("student", password="x")

    def test_anonymous_is_refused_everywhere(self):
        for name, method in ROUTES:
            with self.subTest(route=name):
                response = getattr(self.client, method)(reverse(name))
                self.assertIn(response.status_code, (401, 403), name)

    def test_a_signed_in_non_staff_user_is_refused_everywhere(self):
        self.client.force_login(self.normal)
        for name, method in ROUTES:
            with self.subTest(route=name):
                response = getattr(self.client, method)(reverse(name))
                self.assertEqual(response.status_code, 403, name)

    def test_a_non_staff_user_cannot_WRITE_the_allowlist(self):
        """The one that matters: this endpoint decides what the server fetches."""
        self.client.force_login(self.normal)
        response = self.client.put(
            reverse("admin-allowlist"),
            data=json.dumps({"urls": [{
                "id": "evil", "url": "http://169.254.169.254/latest/meta-data/",
                "label": "cloud metadata", "topics": ["x"], "enabled": True,
            }]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_read(self):
        self.client.force_login(self.staff)
        for name, method in ROUTES:
            with self.subTest(route=name):
                self.assertEqual(getattr(self.client, method)(reverse(name)).status_code, 200)


class AllowlistValidationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", password="x", is_staff=True)
        self.client.force_login(self.staff)

    def _put(self, urls):
        return self.client.put(
            reverse("admin-allowlist"),
            data=json.dumps({"urls": urls}),
            content_type="application/json",
        )

    def test_a_non_http_scheme_is_rejected(self):
        """file:, ftp: and data: are ways to turn a fetcher into something else."""
        with _TempConfig({"institution": {"name": "R"}}):
            response = self._put([{
                "id": "x", "url": "file:///etc/passwd", "label": "L", "topics": ["x"],
            }])
            self.assertEqual(response.status_code, 400)
            self.assertIn("scheme", response.json()["detail"])

    def test_credentials_in_a_url_are_rejected(self):
        with _TempConfig({"institution": {"name": "R"}}):
            response = self._put([{
                "id": "x", "url": "https://user:pw@example.edu/", "label": "L",
                "topics": ["x"],
            }])
            self.assertEqual(response.status_code, 400)
            self.assertIn("credentials", response.json()["detail"])

    def test_private_and_metadata_addresses_are_refused_on_WRITE(self):
        """The fetcher would refuse these at fetch time, so they are inert. They
        are still refused here, because config/institution.json is read by
        operators as a statement of what this system may reach — and a line
        saying 169.254.169.254 is a misleading artefact whether or not it works.
        It also survives into backups, tickets and security reviews, where
        nobody reading it knows the fetcher would refuse."""
        targets = [
            "http://169.254.169.254/latest/meta-data/",   # cloud metadata
            "http://127.0.0.1/",                          # loopback
            "http://[::1]/",                              # loopback, v6
            "http://10.0.0.5/internal",                    # private
            "http://192.168.1.1/",                        # private
            "http://localhost:8000/admin",                # by name
            "https://postgres:5432/",                     # container name
            "https://qdrant.internal/x",                  # reserved suffix
        ]
        with _TempConfig({"institution": {"name": "R"}}):
            for url in targets:
                with self.subTest(url=url):
                    response = self._put([{
                        "id": "x", "url": url, "label": "L", "topics": ["x"],
                    }])
                    self.assertEqual(response.status_code, 400, url)

    def test_a_real_public_url_is_still_accepted(self):
        """The guard must not be so eager that it blocks the actual use case."""
        with _TempConfig({"institution": {"name": "R"}}):
            for url in ("https://www.example.edu/academic-calendar",
                        "https://college.ac.in/notices"):
                with self.subTest(url=url):
                    response = self._put([{
                        "id": "x", "url": url, "label": "L", "topics": ["x"],
                    }])
                    self.assertEqual(response.status_code, 200, url)

    def test_duplicate_ids_are_rejected(self):
        with _TempConfig({"institution": {"name": "R"}}):
            entry = {"id": "same", "url": "https://a.edu/", "label": "L", "topics": ["x"]}
            response = self._put([entry, dict(entry, url="https://b.edu/")])
            self.assertEqual(response.status_code, 400)
            self.assertIn("duplicate", response.json()["detail"])

    def test_all_problems_are_reported_at_once(self):
        """A form should not make an operator fix one field per round trip."""
        with _TempConfig({"institution": {"name": "R"}}):
            response = self._put([
                {"id": "", "url": "file:///x", "label": "", "topics": []},
            ])
            detail = response.json()["detail"]
            self.assertIn("'id' is required", detail)
            self.assertIn("'label' is required", detail)
            self.assertIn("scheme", detail)

    def test_a_valid_save_persists_and_is_readable_back(self):
        with _TempConfig({"institution": {"name": "R"}}) as temp:
            response = self._put([{
                "id": "calendar", "url": "https://example.edu/cal",
                "label": "Calendar", "topics": ["Term Dates"], "enabled": True,
            }])
            self.assertEqual(response.status_code, 200)
            saved = temp.read()["web_sources"]["urls"][0]
            self.assertEqual(saved["url"], "https://example.edu/cal")
            # Topics are lowercased on the way in, because matching is lowercase.
            self.assertEqual(saved["topics"], ["term dates"])

    def test_unknown_fields_are_not_persisted(self):
        """An admin form must not be able to introduce keys the loader has
        never seen."""
        with _TempConfig({"institution": {"name": "R"}}) as temp:
            self._put([{
                "id": "x", "url": "https://a.edu/", "label": "L", "topics": ["t"],
                "follow_redirects": True, "timeout": 9999,
            }])
            saved = temp.read()["web_sources"]["urls"][0]
            self.assertNotIn("follow_redirects", saved)
            self.assertNotIn("timeout", saved)


class WritingConfigIsSafeTests(TestCase):
    """A bad save must not destroy a working configuration."""

    def test_documentation_keys_survive_a_round_trip(self):
        """Editing the allowlist through the UI must not strip the explanation
        of how the allowlist works from the file."""
        with _TempConfig({
            "_README": ["the top-level explanation"],
            "institution": {"name": "R"},
            "web_sources": {"_comment": ["how this works"], "urls": []},
        }) as temp:
            writer.update_section("web_sources", {"urls": [
                {"id": "a", "url": "https://a.edu/", "label": "A", "topics": []},
            ]})
            after = temp.read()
            self.assertIn("_README", after)
            self.assertIn("_comment", after["web_sources"])

    def test_other_sections_are_untouched(self):
        with _TempConfig({
            "institution": {"name": "Riverside", "contact_email": "a@b.edu"},
            "theme": {"accent": "#123456"},
            "web_sources": {"urls": []},
        }) as temp:
            writer.update_section("web_sources", {"urls": []})
            after = temp.read()
            self.assertEqual(after["institution"]["name"], "Riverside")
            self.assertEqual(after["theme"]["accent"], "#123456")

    def test_a_previous_version_is_kept(self):
        with _TempConfig({"institution": {"name": "R"}, "web_sources": {"urls": []}}) as temp:
            writer.update_section("web_sources", {"urls": []})
            self.assertTrue(os.path.exists(temp.path + ".bak"))

    def test_blanking_the_name_is_refused(self):
        with _TempConfig({"institution": {"name": "Riverside"}}) as temp:
            with self.assertRaises(writer.ConfigWriteError):
                writer.update_section(
                    "institution", {"name": "  "}, validate=writer.validate_institution,
                )
            self.assertEqual(temp.read()["institution"]["name"], "Riverside")


class DisablingAnAccountTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", password="x", is_staff=True)
        self.target = User.objects.create_user("leaver", password="x")
        self.client.force_login(self.staff)

    def _post(self, username, active):
        return self.client.post(
            reverse("admin-user-active"),
            data=json.dumps({"username": username, "is_active": active}),
            content_type="application/json",
        )

    def test_disabling_works(self):
        self.assertEqual(self._post("leaver", False).status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_re_enabling_works(self):
        self._post("leaver", False)
        self._post("leaver", True)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_you_cannot_disable_yourself(self):
        """Locking yourself out of the only admin account is recoverable only
        from a shell on the server."""
        response = self._post("boss", False)
        self.assertEqual(response.status_code, 400)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_unknown_user_is_404(self):
        self.assertEqual(self._post("nobody", False).status_code, 404)


class RuntimeSettingsAreReadOnlyTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", password="x", is_staff=True)
        self.client.force_login(self.staff)

    def test_it_says_so_and_says_how_to_change_them(self):
        body = self.client.get(reverse("admin-settings")).json()
        self.assertTrue(body["read_only"])
        self.assertIn("docker compose", body["change_by"])

    def test_it_reports_what_the_process_actually_read(self):
        """From os.environ, not from a file — those differ exactly when it
        matters, which is after an edit with no restart."""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "qwen2.5:3b"}):
            body = self.client.get(reverse("admin-settings")).json()
        models = next(g for g in body["groups"] if g["title"] == "Models")
        entry = next(s for s in models["settings"] if s["key"] == "LLM_MODEL")
        self.assertEqual(entry["value"], "qwen2.5:3b")

    def test_no_write_method_is_offered(self):
        response = self.client.put(
            reverse("admin-settings"), data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)
