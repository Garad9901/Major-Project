# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import ask

urlpatterns = [
    path("", ask, name="ask"),
]
