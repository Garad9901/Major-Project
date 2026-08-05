# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import change_password, csrf, login, logout, me, set_preferences

urlpatterns = [
    path("csrf/", csrf, name="csrf"),
    path("login/", login, name="login"),
    path("logout/", logout, name="logout"),
    path("me/", me, name="me"),
    path("change-password/", change_password, name="change-password"),
    path("preferences/", set_preferences, name="preferences"),
]
