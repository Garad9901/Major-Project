# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import include, path

from orchestrator.views import conversation_detail, conversation_truncate, conversations

urlpatterns = [
    path("api/health/", include("health.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/ask/", include("orchestrator.urls")),
    # Chat history for the sidebar. Mounted here rather than under
    # orchestrator.urls because that module is already mounted at the exact
    # path "api/ask/" and cannot also serve a sibling route.
    path("api/conversations/", conversations, name="conversations"),
    path("api/conversations/<int:pk>/", conversation_detail, name="conversation-detail"),
    # Used by "Regenerate" and "Edit message" to drop the abandoned tail of a
    # thread, so stored history matches what the user actually kept.
    path("api/conversations/<int:pk>/truncate/", conversation_truncate,
         name="conversation-truncate"),
]
