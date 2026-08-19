# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Staff-only endpoints for the things an operator actually changes.

Before this, changing the URL allowlist meant editing JSON on the server and
restarting the backend; disabling a user meant a management command over SSH.
Both are reasonable for the person who built it and unreasonable for the person
who bought it.

SCOPE IS DELIBERATELY NARROW. This is not a general admin panel and
django.contrib.admin is still not installed. Four things are exposed, chosen
because they are what an operator changes during normal running:

    the web-fetch allowlist   was: edit JSON, restart
    user accounts             was: SSH and a management command
    the institution identity  was: edit JSON, restart
    runtime settings          READ ONLY - see below

RUNTIME SETTINGS ARE READ-ONLY ON PURPOSE, AND THAT IS NOT LAZINESS.
Model selection and the demo-data flag are environment variables read once at
process start. A form that appeared to change them would either lie (the value
changes in a file, the process keeps the old one) or require the web server to
restart itself on request, which is a remote-code-execution shape nobody should
build into an admin panel. They are shown, with the exact command to change
them, which is honest and still saves the operator hunting.

EVERY ENDPOINT IS IsStaffUser. The allowlist one decides what the server will
fetch, so a non-staff user reaching it would be an SSRF primitive.
"""

import logging
import os

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsStaffUser
from institution import config as institution_config
from institution import writer

logger = logging.getLogger("administration")

User = get_user_model()


# ------------------------------------------------------------------------------
# The web-fetch allowlist
# ------------------------------------------------------------------------------
@api_view(["GET", "PUT"])
@permission_classes([IsStaffUser])
def allowlist_view(request):
    """Read or replace the complete allowlist.

    REPLACE, not patch. A partial update would need a merge rule, and getting a
    merge rule subtly wrong on the list that decides what the server may fetch
    is a worse failure than making the client send the whole thing.
    """
    if request.method == "GET":
        section = institution_config.get().get("web_sources") or {}
        return Response({
            "urls": [u for u in section.get("urls", []) if isinstance(u, dict)],
            # So the UI can explain why an entry that looks fine is not being
            # used: `enabled: false` is a park, not a delete.
            "note": (
                "The model never sees this list and never supplies a URL. A page "
                "is chosen by keyword matching against 'topics'. Adding an entry "
                "here is the only way this system can reach it."
            ),
        })

    urls = request.data.get("urls")
    if not isinstance(urls, list):
        return Response(
            {"detail": "Expected an object with a 'urls' list."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cleaned = []
    for entry in urls:
        if not isinstance(entry, dict):
            return Response(
                {"detail": "Every allowlist entry must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Whitelist the fields rather than storing what was sent. An admin form
        # should not be able to introduce keys the loader has never seen.
        cleaned.append({
            "id": str(entry.get("id") or "").strip(),
            "url": str(entry.get("url") or "").strip(),
            "label": str(entry.get("label") or "").strip(),
            "topics": [
                str(t).strip().lower()
                for t in (entry.get("topics") or [])
                if str(t).strip()
            ],
            "enabled": bool(entry.get("enabled", True)),
        })

    try:
        writer.update_section(
            "web_sources", {"urls": cleaned}, validate=writer.validate_web_sources,
        )
    except writer.ConfigWriteError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    logger.info(
        "allowlist updated by %s: %d entr%s, %d enabled",
        request.user.username, len(cleaned),
        "y" if len(cleaned) == 1 else "ies",
        sum(1 for c in cleaned if c["enabled"]),
    )
    return Response({"urls": cleaned, "saved": True})


# ------------------------------------------------------------------------------
# The institution's identity
# ------------------------------------------------------------------------------
@api_view(["GET", "PUT"])
@permission_classes([IsStaffUser])
def identity_view(request):
    if request.method == "GET":
        current = institution_config.get()
        return Response({
            "institution": {
                k: v for k, v in (current.get("institution") or {}).items()
                if not k.startswith("_")
            },
            "theme": {
                k: v for k, v in (current.get("theme") or {}).items()
                if not k.startswith("_")
            },
            "problems": institution_config.problems(),
        })

    incoming = request.data.get("institution")
    if not isinstance(incoming, dict):
        return Response(
            {"detail": "Expected an object with an 'institution' key."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    allowed = (
        "name", "short_name", "descriptor", "footnote",
        "initials", "logo_url", "contact_email", "contact_url",
    )
    current = institution_config.get().get("institution") or {}
    merged = {k: v for k, v in current.items() if not k.startswith("_")}
    for key in allowed:
        if key in incoming:
            merged[key] = incoming[key]

    try:
        writer.update_section("institution", merged, validate=writer.validate_institution)
    except writer.ConfigWriteError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    theme = request.data.get("theme")
    if isinstance(theme, dict):
        keep = ("accent", "identity_ink", "identity_highlight")
        current_theme = institution_config.get().get("theme") or {}
        merged_theme = {k: v for k, v in current_theme.items() if not k.startswith("_")}
        for key in keep:
            if key in theme:
                merged_theme[key] = theme[key]
        try:
            writer.update_section("theme", merged_theme)
        except writer.ConfigWriteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    logger.info("institution identity updated by %s", request.user.username)
    return Response({"saved": True, "institution": merged})


# ------------------------------------------------------------------------------
# User accounts
# ------------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsStaffUser])
def users_view(request):
    """List accounts. Creation stays a management command, deliberately.

    create_user generates a password, writes it to a 0600 file and never echoes
    it. Reproducing that over HTTP would mean returning a live credential in a
    JSON response — into browser history, any proxy log and the operator's
    clipboard. The list is the useful half; the command is one line and it is
    linked from the UI.
    """
    rows = []
    for user in User.objects.all().order_by("username").select_related():
        rows.append({
            "username": user.username,
            "email": user.email,
            "full_name": user.get_full_name(),
            "is_staff": user.is_staff,
            "is_active": user.is_active,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        })
    return Response({"users": rows, "count": len(rows)})


@api_view(["POST"])
@permission_classes([IsStaffUser])
def set_user_active_view(request):
    """Enable or disable an account.

    Disabling is the reversible half of account management and the one an
    operator needs in a hurry — someone has left, or an account is suspected
    compromised. Deletion is not offered: it destroys the audit trail's
    reference to who asked what.
    """
    username = str(request.data.get("username") or "").strip()
    active = request.data.get("is_active")
    if not username or not isinstance(active, bool):
        return Response(
            {"detail": "Send 'username' and a boolean 'is_active'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if username == request.user.username and not active:
        # Locking yourself out of the only admin account is recoverable only
        # from a shell on the server.
        return Response(
            {"detail": "You cannot disable your own account while signed in to it."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return Response({"detail": "No such user."}, status=status.HTTP_404_NOT_FOUND)

    user.is_active = active
    user.save(update_fields=["is_active"])

    if not active:
        # A disabled account with a live session is still a signed-in user until
        # that session expires. Revoke immediately.
        try:
            from accounts import sessions
            sessions.revoke_all(user)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "DISABLED %s but could not revoke their sessions: %s", username, exc,
            )
            return Response({
                "saved": True,
                "warning": (
                    "The account is disabled, but existing sessions could not be "
                    "revoked automatically. Restart the backend to clear them."
                ),
            })

    logger.info(
        "account %s %s by %s", username,
        "enabled" if active else "DISABLED and sessions revoked", request.user.username,
    )
    return Response({"saved": True, "username": username, "is_active": active})


# ------------------------------------------------------------------------------
# Runtime settings (read-only)
# ------------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsStaffUser])
def settings_view(request):
    """What the process is actually running with, and how to change it.

    Reported from os.environ rather than from a settings file, so what is shown
    is what this process READ — not what someone believes the file says. Those
    differ exactly when it matters: after an edit with no restart.
    """
    def env(name, default=""):
        return os.getenv(name, default)

    return Response({
        "read_only": True,
        "why_read_only": (
            "These are environment variables read once when the backend started. "
            "Changing them here could not affect the running process, and making "
            "the server restart itself on request is not something an admin panel "
            "should be able to do. Edit the file shown below and restart."
        ),
        "change_by": "Edit .env (or .env.production), then: docker compose up -d backend",
        "groups": [
            {
                "title": "Models",
                "note": "A model must be pulled before it can be selected: docker compose exec ollama ollama pull <name>",
                "settings": [
                    {"key": "LLM_MODEL", "value": env("LLM_MODEL", "qwen2.5:7b"),
                     "description": "Writes the answers. The largest cost in the system."},
                    {"key": "VERIFICATION_MODEL", "value": env("VERIFICATION_MODEL") or "(same as LLM_MODEL)",
                     "description": "Fact-checks each answer. A smaller model here is usually right."},
                    {"key": "ROUTER_MODEL", "value": env("ROUTER_MODEL", "qwen2.5:3b"),
                     "description": "Only reached when the rule and embedding tiers are unsure."},
                    {"key": "EMBEDDING_MODEL", "value": env("EMBEDDING_MODEL", "nomic-embed-text"),
                     "description": "Builds the search index. Changing it requires a full re-index."},
                ],
            },
            {
                "title": "Data",
                "settings": [
                    {"key": "SEED_DEMO_DATA", "value": env("SEED_DEMO_DATA", "false"),
                     "description": "Loads 13,000 invented faculty records into an EMPTY database. Never enable on a server holding real records."},
                ],
            },
            {
                "title": "Behaviour",
                "settings": [
                    {"key": "ENABLE_VERIFICATION", "value": env("ENABLE_VERIFICATION", "true"),
                     "description": "Inline fact-checking. Off is faster and removes the only check on a wrong answer."},
                    {"key": "ASK_RATE_LIMIT", "value": env("ASK_RATE_LIMIT", "10/min"),
                     "description": "Questions per user per period."},
                    {"key": "AUDIT_LOG_RETENTION_DAYS", "value": env("AUDIT_LOG_RETENTION_DAYS", "90"),
                     "description": "A governance decision, not a technical one. The audit log holds question and answer text."},
                ],
            },
        ],
    })
