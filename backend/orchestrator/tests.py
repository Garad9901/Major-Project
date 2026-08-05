# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Cross-user isolation for stored conversations.

THE PROPERTY UNDER TEST
User A must not be able to reach user B's conversations by ANY route the API
offers. Not by guessing an id, not by passing one to /api/ask/, not by listing,
not by deleting.

Isolation here rests on every queryset being filtered by `user=request.user`.
That is one line per view and trivially easy to omit when a view is added later
— which is exactly why it is tested rather than reviewed. These tests fail
loudly the moment a new endpoint forgets the filter.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts.models import UserProfile
from orchestrator.models import Conversation, Message, title_from


def _make_user(username, password="Isolation-Test-Pw-4417"):
    user = User.objects.create_user(username=username, password=password)
    # Cleared so the account can use the API; a fresh account is otherwise
    # blocked until it changes its password (see accounts.permissions).
    UserProfile.objects.update_or_create(
        user=user, defaults={"must_change_password": False}
    )
    return user


class ConversationIsolationTests(TestCase):
    def setUp(self):
        self.password = "Isolation-Test-Pw-4417"
        self.alice = _make_user("alice", self.password)
        self.bob = _make_user("bob", self.password)

        self.alice_convo = Conversation.objects.create(
            user=self.alice, title="Alice private budget question"
        )
        Message.objects.create(
            conversation=self.alice_convo, role="user",
            text="What is the confidential salary band for Professors?",
        )
        Message.objects.create(
            conversation=self.alice_convo, role="assistant",
            text="ALICE ONLY SECRET ANSWER", route="SQL",
        )

        self.bob_convo = Conversation.objects.create(user=self.bob, title="Bob question")
        Message.objects.create(conversation=self.bob_convo, role="user", text="Bob's question")

        self.client_a = Client()
        self.client_a.login(username="alice", password=self.password)
        self.client_b = Client()
        self.client_b.login(username="bob", password=self.password)

    # --- listing --------------------------------------------------------------

    def test_list_returns_only_own_conversations(self):
        resp = self.client_b.get("/api/conversations/")
        self.assertEqual(resp.status_code, 200)
        titles = [c["title"] for c in resp.json()]
        self.assertIn("Bob question", titles)
        self.assertNotIn("Alice private budget question", titles)

    def test_list_ids_do_not_include_other_users(self):
        ids = [c["id"] for c in self.client_b.get("/api/conversations/").json()]
        self.assertNotIn(self.alice_convo.id, ids)

    # --- direct access by id --------------------------------------------------

    def test_cannot_read_another_users_conversation_by_id(self):
        resp = self.client_b.get(f"/api/conversations/{self.alice_convo.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("ALICE ONLY SECRET ANSWER", resp.content.decode())

    def test_owner_can_read_their_own(self):
        resp = self.client_a.get(f"/api/conversations/{self.alice_convo.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ALICE ONLY SECRET ANSWER", resp.content.decode())

    def test_not_found_rather_than_forbidden(self):
        """404, not 403.

        403 on an existing id and 404 on a missing one lets an outsider
        enumerate which conversation ids exist. Both must look identical.
        """
        real_other = self.client_b.get(f"/api/conversations/{self.alice_convo.id}/")
        never_existed = self.client_b.get("/api/conversations/99999999/")
        self.assertEqual(real_other.status_code, never_existed.status_code)
        self.assertEqual(real_other.json(), never_existed.json())

    # --- deletion -------------------------------------------------------------

    def test_cannot_delete_another_users_conversation(self):
        resp = self.client_b.delete(f"/api/conversations/{self.alice_convo.id}/")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(
            Conversation.objects.filter(pk=self.alice_convo.pk).exists(),
            "Alice's conversation was deleted by Bob",
        )

    def test_owner_can_delete_their_own(self):
        resp = self.client_a.delete(f"/api/conversations/{self.alice_convo.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Conversation.objects.filter(pk=self.alice_convo.pk).exists())

    # --- writing into someone else's thread -----------------------------------

    def test_cannot_append_to_another_users_conversation(self):
        """Passing another user's conversation_id to /api/ask/ must not append.

        The pipeline is not exercised here (it would call the model); what
        matters is that the id is not honoured. _get_or_create_conversation
        filters by user, so a foreign id starts a NEW conversation owned by the
        caller instead.
        """
        from orchestrator.views import _get_or_create_conversation

        class _Req:
            def __init__(self, user, data):
                self.user = user
                self.data = data

        before = Message.objects.filter(conversation=self.alice_convo).count()
        convo = _get_or_create_conversation(
            _Req(self.bob, {"conversation_id": self.alice_convo.id}), "sneaky question"
        )
        self.assertIsNotNone(convo)
        self.assertNotEqual(convo.id, self.alice_convo.id)
        self.assertEqual(convo.user_id, self.bob.id)
        self.assertEqual(
            Message.objects.filter(conversation=self.alice_convo).count(), before,
            "a message was written into another user's conversation",
        )

    # --- unauthenticated ------------------------------------------------------

    def test_anonymous_cannot_list_or_read(self):
        anon = Client()
        self.assertIn(anon.get("/api/conversations/").status_code, (401, 403))
        self.assertIn(
            anon.get(f"/api/conversations/{self.alice_convo.id}/").status_code, (401, 403)
        )

    def test_logging_out_ends_access(self):
        self.assertEqual(
            self.client_a.get(f"/api/conversations/{self.alice_convo.id}/").status_code, 200
        )
        self.client_a.post("/api/auth/logout/")
        self.assertIn(
            self.client_a.get(f"/api/conversations/{self.alice_convo.id}/").status_code,
            (401, 403),
        )


class HistoryPersistenceTests(TestCase):
    """History is server-side, so it must survive logout and follow the account
    onto a different client."""

    def setUp(self):
        self.password = "Isolation-Test-Pw-4417"
        self.user = _make_user("carol", self.password)

    def test_history_survives_logout_and_a_new_device(self):
        convo = Conversation.objects.create(user=self.user, title="Carol earlier chat")
        Message.objects.create(conversation=convo, role="user", text="first question")
        Message.objects.create(conversation=convo, role="assistant", text="first answer")

        first_device = Client()
        first_device.login(username="carol", password=self.password)
        self.assertEqual(len(first_device.get("/api/conversations/").json()), 1)
        first_device.post("/api/auth/logout/")

        # A different client object == a different browser, with no cookies or
        # storage carried over from the first.
        second_device = Client()
        second_device.login(username="carol", password=self.password)
        listed = second_device.get("/api/conversations/").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["title"], "Carol earlier chat")

        detail = second_device.get(f"/api/conversations/{convo.id}/").json()
        self.assertEqual([m["text"] for m in detail["messages"]],
                         ["first question", "first answer"])


class TitleTests(TestCase):
    def test_title_is_derived_and_bounded(self):
        self.assertEqual(title_from("Short question?"), "Short question?")
        self.assertEqual(title_from(""), "New chat")
        long_title = title_from("word " * 100)
        self.assertLessEqual(len(long_title), 61)
        self.assertTrue(long_title.endswith("…"))

    def test_title_collapses_newlines(self):
        self.assertNotIn("\n", title_from("line one\nline two\n\nline three"))
