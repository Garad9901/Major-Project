# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Guards on the options every Ollama call carries.

WHY THESE EXIST AT ALL
`num_ctx` reads like a performance setting and is not one. Ollama silently
discards the FRONT of any prompt that exceeds the context window, and the front
of a synthesis prompt is the system prompt — including the "# UNTRUSTED
CONTENT" rules that stop a poisoned database field from redirecting the model.
Measured before this was fixed: an ~11,000-token prompt sent with num_ctx=4096
came back with prompt_eval_count=2050 and the model unable to see a canary
placed in the first line.

So a future change that drops these options, or that sets a different num_ctx
per agent, is a security regression rather than a slower system. That is worth
a test that fails loudly.
"""

from unittest import mock

from django.test import SimpleTestCase

from common import ollama


class _FakeResponse:
    """Minimal stand-in for requests.Response for the non-streaming path."""

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body

    def close(self):
        return None


def _captured_options(**patch):
    """Make one chat() call and return the options dict that reached Ollama."""
    seen = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        seen.update(json["options"])
        return _FakeResponse({"message": {"content": "ok"}})

    with mock.patch.multiple(ollama, **patch):
        with mock.patch.object(ollama.requests, "post", fake_post):
            ollama.chat("qwen2.5:7b", messages=[{"role": "user", "content": "hi"}])
    return seen


class ContextWindowIsAlwaysSentTests(SimpleTestCase):
    def test_num_ctx_is_sent_on_every_chat_call(self):
        options = _captured_options(NUM_CTX=8192, NUM_THREAD=0)
        self.assertEqual(options.get("num_ctx"), 8192)

    def test_num_ctx_has_headroom_over_the_largest_measured_prompt(self):
        """3,365 tokens was the largest single prompt across 300 real questions.

        This asserts the shipped default, not the patched one — someone lowering
        NUM_CTX back towards the old 4096 default should have to change a test
        that explains why that is dangerous.
        """
        self.assertGreaterEqual(
            ollama.NUM_CTX, 2 * 3365,
            "num_ctx must keep at least 2x headroom over the largest measured "
            "prompt; below it Ollama silently truncates the system prompt away",
        )

    def test_an_agent_can_still_override(self):
        """setdefault, not force — an agent with a reason keeps its own value."""
        seen = {}

        def fake_post(url, json=None, timeout=None, **kwargs):
            seen.update(json["options"])
            return _FakeResponse({"message": {"content": "ok"}})

        with mock.patch.object(ollama.requests, "post", fake_post):
            ollama.chat(
                "qwen2.5:7b",
                messages=[{"role": "user", "content": "hi"}],
                options={"num_ctx": 2048, "temperature": 0},
            )
        self.assertEqual(seen["num_ctx"], 2048)
        self.assertEqual(seen["temperature"], 0)

    def test_caller_options_survive_the_merge(self):
        seen = {}

        def fake_post(url, json=None, timeout=None, **kwargs):
            seen.update(json["options"])
            return _FakeResponse({"message": {"content": "ok"}})

        with mock.patch.object(ollama.requests, "post", fake_post):
            ollama.chat(
                "qwen2.5:7b",
                messages=[{"role": "user", "content": "hi"}],
                options={"temperature": 0.2, "num_predict": 900},
            )
        self.assertEqual(seen["temperature"], 0.2)
        self.assertEqual(seen["num_predict"], 900)
        self.assertEqual(seen["num_ctx"], ollama.NUM_CTX)


class ThreadCountIsOptOutTests(SimpleTestCase):
    """num_thread defaults to auto because the measured gain (1.12x prefill,
    n=3) does not justify hardcoding a core count that suits one machine."""

    def test_zero_means_do_not_send_it(self):
        options = _captured_options(NUM_CTX=8192, NUM_THREAD=0)
        self.assertNotIn("num_thread", options)

    def test_a_positive_value_is_sent(self):
        options = _captured_options(NUM_CTX=8192, NUM_THREAD=14)
        self.assertEqual(options.get("num_thread"), 14)


class StreamingCarriesTheSameOptionsTests(SimpleTestCase):
    """The streaming path is the one synthesis actually uses, and synthesis has
    the largest prompt of any agent. If only chat() were guarded, the agent most
    at risk of truncation would be the one left unprotected."""

    def test_stream_sends_num_ctx(self):
        seen = {}

        class _FakeStream(_FakeResponse):
            def iter_lines(self):
                import json as _json
                yield _json.dumps({"message": {"content": "hi"}, "done": False}).encode()
                yield _json.dumps({"message": {"content": ""}, "done": True}).encode()

        def fake_post(url, json=None, timeout=None, stream=None, **kwargs):
            seen.update(json["options"])
            return _FakeStream({})

        with mock.patch.object(ollama.requests, "post", fake_post):
            list(ollama.chat_stream("qwen2.5:7b", messages=[{"role": "user", "content": "hi"}]))
        self.assertEqual(seen.get("num_ctx"), ollama.NUM_CTX)
