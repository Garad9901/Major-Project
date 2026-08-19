# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Serves the institution's identity to the browser.

UNAUTHENTICATED ON PURPOSE, AND THAT IS THE WHOLE DESIGN CONSTRAINT.
The sign-in screen shows the institution's name, monogram and colours, and it
renders before anyone has signed in. So this endpoint cannot require a session,
and therefore nothing sensitive may ever be added to it. `config.public()` is an
allowlist rather than a blocklist for exactly that reason — a field added to
institution.json is not published here until someone writes it into that
function deliberately.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import config


@api_view(["GET"])
@permission_classes([AllowAny])
def institution_view(request):
    # Cached in-process by config.get(); this is read on every sign-in page
    # load, including by users who then fail to sign in.
    return Response(config.public())
