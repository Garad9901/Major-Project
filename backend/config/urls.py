# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import include, path

from orchestrator.views import conversation_detail, conversations

urlpatterns = [
    path("api/health/", include("health.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/ask/", include("orchestrator.urls")),
    # Chat history for the sidebar. Mounted here rather than under
    # orchestrator.urls because that module is already mounted at the exact
    # path "api/ask/" and cannot also serve a sibling route.
    path("api/conversations/", conversations, name="conversations"),
    path("api/conversations/<int:pk>/", conversation_detail, name="conversation-detail"),
]
