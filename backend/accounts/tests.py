# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Session lifetime, and the operator-driven password reset."""

from importlib import import_module
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase

from django.db import DatabaseError

from accounts import lockout, sessions
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

    # THESE TWO WERE REWRITTEN when sessions moved from Postgres to Redis.
    #
    # They used to read and write `Session.objects`, the database model. That
    # table is empty now, so the old versions raised Session.DoesNotExist —
    # loudly, which is the good case. The bad case would have been a test that
    # kept passing while testing nothing, so they are rewritten against the
    # configured session store rather than deleted.

    def test_session_is_stored_in_the_cache_not_the_database(self):
        """The whole point of the change, asserted directly."""
        key = self.client.session.session_key
        self.assertFalse(
            Session.objects.filter(session_key=key).exists(),
            "session was written to Postgres — SESSION_ENGINE is not cache-backed",
        )
        self.assertIn("cache", settings.SESSION_ENGINE)

    def test_expired_session_is_rejected(self):
        """Expiry for a cache-backed session IS the cache key expiring."""
        store = import_module(settings.SESSION_ENGINE).SessionStore
        key = self.client.session.session_key
        store(session_key=key).delete()
        self.assertIn(self.client.get("/api/conversations/").status_code, (401, 403))

    def test_activity_extends_the_session(self):
        """A request must push the expiry further out, or it is not idle-based.

        Reads the key's TTL straight from Redis. Django's cache API has no
        getter for a remaining TTL, so this reaches for the underlying client —
        acceptable here because the assertion is specifically about expiry
        behaviour, which is what a session timeout is.
        """
        key = self.client.session.session_key
        cache_key = f"django.contrib.sessions.cache{key}"
        client = cache._cache.get_client()
        full_key = cache.make_key(cache_key)

        client.expire(full_key, 60)  # pretend only a minute is left
        shortened = client.ttl(full_key)
        self.client.get("/api/conversations/")
        after = client.ttl(full_key)

        self.assertGreater(
            after, shortened,
            "activity did not re-stamp the session TTL — the timeout is not idle-based",
        )


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
        """REWRITTEN: Redis is now authoritative, so the lock expires there.

        The old version aged `profile.locked_until` into the past and expected
        the lock to lift. It no longer does, and that is correct rather than a
        regression: if backdating a database column could unlock an account,
        the Redis counter would not be authoritative at all and the fallback
        ordering in accounts/lockout.py would be the wrong way round.

        Expiry in Redis is the key's TTL, so this deletes the key — which is
        what the TTL does a quarter of an hour later.
        """
        for _ in range(5):
            self._attempt("wrong")
        self.assertTrue(lockout.is_locked(profile_for(self.user)))

        cache.delete(lockout._lock_key("frank"))
        cache.delete(lockout._fail_key("frank"))

        self.assertFalse(lockout.is_locked(profile_for(self.user)))
        self.assertEqual(self._attempt(PW).status_code, 200)

    def test_lock_survives_a_cache_outage_via_the_profile(self):
        """FAILS CLOSED. Losing Redis must not unlock a locked account.

        The mirrored profile column exists for exactly this: if the cache
        cannot be read, the lock is still known. The alternative — failing open
        — would hand an attacker a clean slate by taking Redis down, which is a
        strictly easier attack than guessing the password.
        """
        for _ in range(5):
            self._attempt("wrong")
        profile = profile_for(self.user)
        self.assertIsNotNone(profile.locked_until, "lock was not mirrored to the profile")

        with mock.patch("accounts.lockout.cache") as broken:
            broken.get.side_effect = RuntimeError("redis is down")
            self.assertTrue(
                lockout.is_locked(profile_for(self.user)),
                "a cache outage unlocked a locked account",
            )

    def test_counter_lives_in_the_cache_not_only_the_database(self):
        """A failed login must not require a write to the records database."""
        self._attempt("wrong")
        self.assertEqual(cache.get(lockout._fail_key("frank")), 1)

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


class SessionRevocationTests(TestCase):
    """Forcibly signing one user out, now that sessions are not database rows.

    This is incident-response tooling: it is used when an account is believed
    compromised. The previous implementation scanned `django_session`, which
    became an empty table the moment sessions moved to Redis — so it would have
    reported "destroyed 0 sessions" and left the attacker signed in. These
    tests exist so that cannot happen again unnoticed.
    """

    def setUp(self):
        cache.clear()
        self.user = _make_user("grace")
        self.other = _make_user("heidi")

    def _signed_in(self, username):
        c = Client()
        c.login(username=username, password=PW)
        return c

    def test_revoke_all_ends_a_live_session(self):
        c = self._signed_in("grace")
        self.assertEqual(c.get("/api/conversations/").status_code, 200)

        destroyed = sessions.revoke_all(self.user)

        self.assertEqual(destroyed, 1)
        self.assertIn(c.get("/api/conversations/").status_code, (401, 403))

    def test_revoke_all_reports_a_truthful_count(self):
        """Not 'number of keys in the index' — number actually destroyed."""
        self._signed_in("grace")
        self._signed_in("grace")
        self.assertEqual(sessions.revoke_all(self.user), 2)
        # Second call finds them already gone and must not double-count.
        self.assertEqual(sessions.revoke_all(self.user), 0)

    def test_revoking_one_user_does_not_touch_another(self):
        grace = self._signed_in("grace")
        heidi = self._signed_in("heidi")

        sessions.revoke_all(self.user)

        self.assertIn(grace.get("/api/conversations/").status_code, (401, 403))
        self.assertEqual(heidi.get("/api/conversations/").status_code, 200,
                         "revoking one account signed out an unrelated user")

    def test_login_indexes_the_session_key(self):
        """The signal has to be connected, or revocation finds nothing.

        Worth its own test because the failure mode is silent: an unconnected
        receiver leaves an empty index and revoke_all() returns 0 without
        raising anything.
        """
        c = self._signed_in("grace")
        indexed = cache.get(f"user-sessions:{self.user.pk}") or []
        self.assertIn(c.session.session_key, indexed)

    def test_disable_user_command_still_revokes(self):
        c = self._signed_in("grace")
        call_command("disable_user", "grace", stdout=StringIO())
        self.assertIn(c.get("/api/conversations/").status_code, (401, 403))

    def test_revocation_survives_an_empty_index(self):
        """The index is a convenience; the auth hash is the guarantee.

        Even with the index wiped — a Redis restart, a bug, anything — changing
        the password must still end every session, because Django re-derives
        the session auth hash from the password on every request. This is the
        mechanism that has no single point of failure, so it is tested
        separately from the index.
        """
        c = self._signed_in("grace")
        cache.delete(f"user-sessions:{self.user.pk}")

        self.user.set_password("A-Completely-Different-9134")
        self.user.save(update_fields=["password"])

        self.assertIn(c.get("/api/conversations/").status_code, (401, 403))


class LoginDuringDatabaseOutageTests(TestCase):
    """A new sign-in during a Postgres outage must fail CLEANLY.

    It is expected to fail: the password hash lives in Postgres and cannot be
    checked without it. That is not the resilience gap Redis sessions were
    added to fix, and it is not treated as one.

    What was unacceptable was the SHAPE of the failure — an unhandled
    OperationalError became a 500, which in development rendered a 198 KB debug
    traceback. A 503 with a plain sentence says the same thing honestly.
    """

    def setUp(self):
        cache.clear()
        _make_user("ivan")

    def test_database_error_is_a_503_not_a_500(self):
        with mock.patch("accounts.views.authenticate", side_effect=DatabaseError("down")):
            resp = Client().post(
                "/api/auth/login/",
                data={"username": "ivan", "password": PW},
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 503)

    def test_the_message_is_useful_and_leaks_nothing(self):
        with mock.patch("accounts.views.authenticate",
                        side_effect=DatabaseError('FATAL: role "x" does not exist')):
            resp = Client().post(
                "/api/auth/login/",
                data={"username": "ivan", "password": PW},
                content_type="application/json",
            )
        body = resp.json()["error"]
        self.assertIn("temporarily unavailable", body)
        # The database's own error text must not reach the user.
        self.assertNotIn("FATAL", body)
        self.assertNotIn("role", body)
        # It should tell an already-signed-in user they are unaffected, which
        # is the whole point of the Redis change.
        self.assertIn("already signed in", body)
