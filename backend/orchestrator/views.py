# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import time

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import CanUseAssistant
from accounts.throttling import AskRateThrottle
from audit.models import AuditLog
from common.exceptions import ServiceUnavailable

from .models import Conversation, Message, title_from
from .sanitize import QuestionRejected, sanitize_question
from .service import answer_question_stream

logger = logging.getLogger("orchestrator")

# Polite, non-technical replies for input problems — shown as a normal
# assistant message rather than an error, so the chat never "errors out".
POLITE_MESSAGES = {
    "empty": (
        "It looks like your message was empty. Please type a question about "
        "courses, departments, faculty, fees, or schedules."
    ),
    "too_long": (
        "That question is a bit long (the limit is 500 characters). Please "
        "shorten it and try again."
    ),
}
GENERIC_ERROR = "Something went wrong while answering. Please try again in a moment."


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _client_ip(request):
    # Behind the Caddy proxy the real client is the first X-Forwarded-For hop.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


_AGENTS_FOR_ROUTE = {"SQL": "sql", "RAG": "rag", "BOTH": "sql+rag"}


@api_view(["POST"])
# Since Phase 4 this is CanUseAssistant, not IsStaffUser: students hold
# non-staff accounts and are legitimate users. The permission still requires an
# active session AND that the initial operator-issued password has been changed.
@permission_classes([CanUseAssistant])
@throttle_classes([AskRateThrottle])
def ask(request):
    username = getattr(request.user, "username", "") or "anonymous"
    client_ip = _client_ip(request)
    raw_question = request.data.get("question")

    try:
        question, injection_flags = sanitize_question(raw_question)
    except QuestionRejected as exc:
        # Respond politely (as a normal assistant reply) instead of erroring out.
        message = POLITE_MESSAGES.get(exc.code, POLITE_MESSAGES["empty"])
        _write_audit(
            username=username, client_ip=client_ip,
            question=(str(raw_question or "")[:500]), meta={},
            answer=message, injection_flags=[], latency_ms=0.0,
        )
        return _sse_stream(_polite_events(message))

    started = time.perf_counter()

    # Chat history. Failing to record a conversation must never cost the user
    # their answer, so every persistence call here is best-effort — same rule as
    # the audit write below, for the same reason.
    conversation = _get_or_create_conversation(request, question)
    _add_message(conversation, "user", question)

    def event_stream():
        meta = {}
        answer_parts = []
        final_answer = None

        # Emitted before anything else so the SPA can attach this exchange to a
        # conversation immediately — including a brand-new one, whose id it
        # cannot know until now.
        if conversation is not None:
            yield _sse("conversation", {
                "id": conversation.id,
                "title": conversation.title,
            })
        try:
            for kind, payload in answer_question_stream(question):
                if kind == "meta":
                    meta = payload
                elif kind == "token":
                    answer_parts.append(payload)
                    yield _sse("token", {"text": payload})
                    continue
                elif kind == "done":
                    final_answer = payload.get("answer", "".join(answer_parts))
                yield _sse(kind, payload)
        except ServiceUnavailable as exc:
            # A backing service is down — show the safe user_message, never the
            # raw connection error. The technical detail is logged below.
            logger.warning("service unavailable for question=%r: %s", question, exc)
            final_answer = exc.user_message
            yield _sse("error", {"error": exc.user_message})
        except Exception:
            logger.exception("unexpected error answering question=%r", question)
            final_answer = GENERIC_ERROR
            yield _sse("error", {"error": GENERIC_ERROR})
        finally:
            answer = final_answer if final_answer is not None else "".join(answer_parts)
            _write_audit(
                username=username,
                client_ip=client_ip,
                question=question,
                meta=meta,
                answer=answer,
                injection_flags=injection_flags,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            # Runs even when the client disconnects mid-stream (Django closes the
            # generator, which raises GeneratorExit through this finally), so a
            # partial answer is still saved rather than lost.
            _add_message(conversation, "assistant", answer, route=(meta or {}).get("route") or "")

    return _sse_stream(event_stream())


def _polite_events(message):
    # A minimal SSE stream that delivers a single assistant message.
    yield _sse("meta", {"route": None, "degraded": False})
    yield _sse("token", {"text": message})
    yield _sse("done", {"answer": message})


def _sse_stream(generator):
    response = StreamingHttpResponse(generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable proxy buffering so tokens flush immediately
    return response


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------
# All best-effort: a failure here degrades the sidebar, never the answer.


def _get_or_create_conversation(request, question):
    """The conversation this question belongs to, creating one if needed.

    An explicit conversation_id is filtered by `user=request.user`, so passing
    someone else's id returns nothing and starts a fresh conversation rather
    than appending to — or leaking — a stranger's chat.
    """
    try:
        raw_id = request.data.get("conversation_id")
        if raw_id:
            existing = Conversation.objects.filter(pk=raw_id, user=request.user).first()
            if existing:
                return existing
        return Conversation.objects.create(
            user=request.user, title=title_from(question)
        )
    except Exception:
        logger.exception("could not open a conversation for username=%r", request.user)
        return None


def _add_message(conversation, role, text, route=""):
    if conversation is None:
        return
    try:
        Message.objects.create(
            conversation=conversation, role=role, text=text or "", route=route or ""
        )
        # Touch the parent so the sidebar orders by most recent activity.
        conversation.save(update_fields=["updated_at"])
    except Exception:
        logger.exception("could not save %s message to conversation %s", role, conversation.pk)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def conversations(request):
    """The signed-in user's conversations, most recently active first."""
    rows = Conversation.objects.filter(user=request.user).values(
        "id", "title", "updated_at"
    )[:200]
    return Response([
        {"id": r["id"], "title": r["title"], "updated_at": r["updated_at"]}
        for r in rows
    ])


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def conversation_detail(request, pk):
    """Read or delete one conversation.

    Scoped to request.user, so another account's id is a 404 rather than a
    permission error — which would confirm the id exists.
    """
    convo = Conversation.objects.filter(pk=pk, user=request.user).first()
    if convo is None:
        return Response({"error": "Not found."}, status=404)

    if request.method == "DELETE":
        # Only the user's own copy goes. The audit record of these questions is
        # a separate table and is deliberately untouched — see orchestrator/models.py.
        convo.delete()
        return Response(status=204)

    return Response({
        "id": convo.id,
        "title": convo.title,
        "messages": [
            {"role": m.role, "text": m.text, "route": m.route}
            for m in convo.messages.all()
        ],
    })


def _write_audit(*, username, client_ip, question, meta, answer, injection_flags, latency_ms):
    # Never let an audit-write failure break the user's answer — log and move on.
    try:
        route = meta.get("route") or "" if meta else ""
        sql_meta = (meta or {}).get("sql") or {}
        AuditLog.objects.create(
            username=username,
            client_ip=client_ip,
            question=question,
            route=route,
            agents_used=_AGENTS_FOR_ROUTE.get(route, ""),
            generated_sql=sql_meta.get("generated_sql"),
            final_answer=answer,
            injection_flags=", ".join(injection_flags),
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("failed to write audit log for question=%r", question)
