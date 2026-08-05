# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Session lifetime, and the operator-driven password reset."""

from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from accounts import lockout
from accounts.models import UserProfile, profile_for

PW = "Session-Test-Pw-8823"


def _make_user(username):
    user = User.objects.create_user(username=username, password=PW)
    UserProfile.objects.update_or_create(
        user=user, defaults={"must_change_password": False}
    )
    return user


class SessionTimeoutTests(TestCase):
    def setUp(self):
        self.user = _make_user("dana")
        self.client = Client()
        self.client.login(username="dana", password=PW)

    def test_timeout_is_configured_as_an_IDLE_timeout(self):
        """Both settings, not just one.

        SESSION_COOKIE_AGE alone is a hard cap measured from login, which would
        eject someone mid-question. SESSION_SAVE_EVERY_REQUEST re-stamps expiry
        on activity, which is what makes it an inactivity timeout.
        """
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_session_cookie_is_httponly(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_active_session_works(self):
        self.assertEqual(self.client.get("/api/conversations/").status_code, 200)

    def test_expired_session_is_rejected(self):
        session = Session.objects.get(session_key=self.client.session.session_key)
        session.expire_date = timezone.now() - timedelta(minutes=1)
        session.save()
        self.assertIn(self.client.get("/api/conversations/").status_code, (401, 403))

    def test_activity_extends_the_session(self):
        """A request must push the expiry further out, or it is not idle-based."""
        key = self.client.session.session_key
        before = Session.objects.get(session_key=key).expire_date
        Session.objects.filter(session_key=key).update(
            expire_date=timezone.now() + timedelta(minutes=5)
        )
        self.client.get("/api/conversations/")
        after = Session.objects.get(session_key=key).expire_date
        self.assertGreater(after, before - timedelta(seconds=1))


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = _make_user("erin")

    def _reset(self, *args):
        out = StringIO()
        call_command("reset_password", "erin", *args, stdout=out)
        text = out.getvalue()
        # The command prints the temporary password; recover it for assertions.
        for line in text.splitlines():
            if "Temporary password:" in line:
                return line.split("Temporary password:")[1].strip(), text
        raise AssertionError(f"no password in output:\n{text}")

    def test_reset_changes_the_password_and_forces_a_change(self):
        old_hash = User.objects.get(username="erin").password
        new_password, _ = self._reset()

        user = User.objects.get(username="erin")
        self.assertNotEqual(user.password, old_hash)
        self.assertTrue(user.check_password(new_password))
        self.assertTrue(profile_for(user).must_change_password)

    def test_generated_password_passes_the_validators(self):
        from django.contrib.auth.password_validation import validate_password
        new_password, _ = self._reset()
        validate_password(new_password, user=User.objects.get(username="erin"))

    def test_password_is_never_stored_in_plaintext(self):
        new_password, _ = self._reset()
        stored = User.objects.get(username="erin").password
        self.assertNotIn(new_password, stored)
        self.assertTrue(stored.startswith("pbkdf2_"), stored.split("$")[0])

    def test_reset_ends_existing_sessions(self):
        """End to end: after a reset, an already-signed-in client is out."""
        signed_in = Client()
        signed_in.login(username="erin", password=PW)
        self.assertEqual(signed_in.get("/api/conversations/").status_code, 200)

        self._reset()

        self.assertIn(signed_in.get("/api/conversations/").status_code, (401, 403))

    def test_password_change_alone_invalidates_sessions(self):
        """Django does this for us, and the docs for this command now say so.

        A --keep-sessions flag was written on the assumption that it did not.
        This test is what disproved that, so it stays as the record: no
        session row is deleted here, only the password is changed.
        """
        signed_in = Client()
        signed_in.login(username="erin", password=PW)
        self.assertEqual(signed_in.get("/api/conversations/").status_code, 200)

        user = User.objects.get(username="erin")
        user.set_password("Different-Password-5591")
        user.save(update_fields=["password"])

        self.assertIn(signed_in.get("/api/conversations/").status_code, (401, 403))

    def test_unknown_user_is_an_error(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("reset_password", "nobody-here", stdout=StringIO())


class BruteForceLockoutTests(TestCase):
    """5 failed attempts, then 15 minutes locked."""

    def setUp(self):
        # The per-IP login throttle (10/min) lives in Django's cache, which is
        # NOT reset between tests — so a class that makes five or six login
        # attempts per test starts tripping 429 partway through the run and the
        # failures look like lockout bugs. Clearing it isolates the behaviour
        # under test from the throttle, which has its own tests elsewhere.
        cache.clear()
        self.user = _make_user("frank")
        self.client = Client()

    def _attempt(self, password):
        # CSRF is enforced on login (see accounts/authentication.py), and the
        # Django test client handles it unless enforce_csrf_checks is set.
        return self.client.post(
            "/api/auth/login/",
            data={"username": "frank", "password": password},
            content_type="application/json",
        )

    def test_locks_after_five_failures(self):
        for i in range(4):
            self.assertEqual(self._attempt("wrong").status_code, 401, f"attempt {i+1}")
            self.assertFalse(lockout.is_locked(profile_for(self.user)))

        self.assertEqual(self._attempt("wrong").status_code, 401)
        self.assertTrue(lockout.is_locked(profile_for(self.user)),
                        "account should be locked after 5 failures")

    def test_correct_password_is_refused_while_locked(self):
        for _ in range(5):
            self._attempt("wrong")
        resp = self._attempt(PW)
        self.assertEqual(resp.status_code, 423)
        self.assertIn("temporarily locked", resp.json()["error"])

    def test_lock_is_not_disclosed_to_a_guesser(self):
        """A wrong password must look identical whether or not the account is
        locked, or the lock becomes an account-exists oracle."""
        unlocked_wrong = self._attempt("wrong")
        for _ in range(5):
            self._attempt("wrong")
        locked_wrong = self._attempt("still-wrong")
        self.assertEqual(unlocked_wrong.status_code, locked_wrong.status_code)
        self.assertEqual(unlocked_wrong.json(), locked_wrong.json())

    def test_lock_expires(self):
        for _ in range(5):
            self._attempt("wrong")
        profile = profile_for(self.user)
        self.assertTrue(lockout.is_locked(profile))

        profile.locked_until = timezone.now() - timedelta(seconds=1)
        profile.save(update_fields=["locked_until"])

        self.assertFalse(lockout.is_locked(profile_for(self.user)))
        self.assertEqual(self._attempt(PW).status_code, 200)

    def test_successful_login_clears_the_counter(self):
        for _ in range(3):
            self._attempt("wrong")
        self.assertEqual(profile_for(self.user).failed_login_attempts, 3)
        self.assertEqual(self._attempt(PW).status_code, 200)
        self.assertEqual(profile_for(self.user).failed_login_attempts, 0)

    def test_unknown_username_does_not_error(self):
        """Guessing a non-existent account must behave like any other failure."""
        for _ in range(6):
            resp = self.client.post(
                "/api/auth/login/",
                data={"username": "no-such-person", "password": "x"},
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 401)

    def test_lockout_survives_a_restart(self):
        """State is on the row, not in per-process memory: a cache-backed
        counter would be cleared by any restart."""
        for _ in range(5):
            self._attempt("wrong")
        reloaded = UserProfile.objects.get(user=self.user)
        self.assertIsNotNone(reloaded.locked_until)
        self.assertGreaterEqual(reloaded.failed_login_attempts, 5)


class LoginCsrfTests(TestCase):
    """Regression cover for the login-CSRF vulnerability."""

    def setUp(self):
        # The per-IP login throttle (10/min) lives in Django's cache, which is
        # NOT reset between tests — so a class that makes five or six login
        # attempts per test starts tripping 429 partway through the run and the
        # failures look like lockout bugs. Clearing it isolates the behaviour
        # under test from the throttle, which has its own tests elsewhere.
        cache.clear()
        self.user = _make_user("grace")

    def test_login_without_a_csrf_token_is_rejected(self):
        strict = Client(enforce_csrf_checks=True)
        resp = strict.post(
            "/api/auth/login/",
            data={"username": "grace", "password": PW},
            content_type="application/json",
        )
        self.assertEqual(
            resp.status_code, 403,
            "login accepted a request with no CSRF token — this is login CSRF",
        )

    def test_login_with_a_valid_csrf_token_succeeds(self):
        strict = Client(enforce_csrf_checks=True)
        strict.get("/api/auth/csrf/")
        token = strict.cookies["csrftoken"].value
        resp = strict.post(
            "/api/auth/login/",
            data={"username": "grace", "password": PW},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(resp.status_code, 200)


class LoginThrottleCountsFailuresOnlyTests(TestCase):
    """The per-IP login throttle must not punish a legitimate morning rush.

    Regression for a production audit finding. The throttle counted EVERY login
    attempt, and a 50-user load test produced 40 rejections reading "Request was
    throttled. Expected available in 53 seconds." Behind a campus NAT every
    student shares one public IP, so 10/min applied to the whole institute
    rather than to each person — a 9am sign-in rush was indistinguishable from
    an attack, and would have presented as an outage.

    Counting only FAILURES separates the two: a rush is nearly all successes, a
    credential-stuffing run is nearly all failures.
    """

    def setUp(self):
        cache.clear()

    def _login(self, username, password):
        return Client().post(
            "/api/auth/login/",
            data={"username": username, "password": password},
            content_type="application/json",
        )

    def test_many_successful_logins_from_one_ip_are_never_throttled(self):
        """The case that was broken: 50 people signing in at once."""
        users = [_make_user(f"rush{i:02d}") for i in range(50)]
        for i, _u in enumerate(users):
            resp = self._login(f"rush{i:02d}", PW)
            self.assertEqual(
                resp.status_code, 200,
                f"user {i} was rejected with {resp.status_code}: {resp.content[:120]}",
            )

    def test_repeated_failures_from_one_ip_are_still_throttled(self):
        """The protection must survive the fix."""
        _make_user("victim")
        codes = [self._login("victim", "wrong-password").status_code for _ in range(14)]
        self.assertIn(429, codes, f"no 429 in 14 failed attempts: {codes}")
        # The first ten are charged, the rest are refused outright.
        self.assertEqual(codes[:10], [401] * 10, codes)

    def test_failures_against_unknown_usernames_are_also_charged(self):
        """Otherwise guessing usernames would be a free budget."""
        codes = [self._login(f"nobody{i}", "x").status_code for i in range(14)]
        self.assertIn(429, codes, f"no 429 for unknown usernames: {codes}")

    def test_a_success_does_not_clear_an_existing_failure_budget(self):
        """A valid credential must not be usable to reset the counter and keep
        guessing — otherwise one known-good account launders unlimited attempts
        against every other one."""
        _make_user("honest")
        _make_user("target")
        for _ in range(9):
            self.assertEqual(self._login("target", "wrong-password").status_code, 401)
        # A genuine sign-in in the middle of that run.
        self.assertEqual(self._login("honest", PW).status_code, 200)
        # The tenth failure exhausts the budget; the eleventh is refused.
        self.assertEqual(self._login("target", "wrong-password").status_code, 401)
        self.assertEqual(self._login("target", "wrong-password").status_code, 429)
