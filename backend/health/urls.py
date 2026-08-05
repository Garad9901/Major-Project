# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .status_view import status_page
from .views import health_check, liveness

urlpatterns = [
    path("", health_check, name="health-check"),
    path("live/", liveness, name="health-live"),
    # Human-readable dashboard. HTML, self-refreshing, 503 when degraded.
    path("status/", status_page, name="health-status"),
]
