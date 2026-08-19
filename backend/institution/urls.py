# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import institution_view

urlpatterns = [
    path("", institution_view, name="institution"),
]
