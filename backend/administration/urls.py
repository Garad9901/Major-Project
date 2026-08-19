# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from . import views

urlpatterns = [
    path("allowlist/", views.allowlist_view, name="admin-allowlist"),
    path("identity/", views.identity_view, name="admin-identity"),
    path("users/", views.users_view, name="admin-users"),
    path("users/active/", views.set_user_active_view, name="admin-user-active"),
    path("settings/", views.settings_view, name="admin-settings"),
]
