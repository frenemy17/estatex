from __future__ import annotations

import os
import secrets
import sys
from typing import Optional

from fastapi import Header, HTTPException

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")


async def require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> bool:
    """Guard destructive and expensive routes.

    Deliberately fails closed: with no ``ADMIN_TOKEN`` configured, admin routes
    are unreachable rather than open. A public deploy therefore starts read-only.
    """
    srv = sys.modules.get("server")
    expected = (
        getattr(srv, "ADMIN_TOKEN", None)
        if srv and getattr(srv, "ADMIN_TOKEN", None) is not None
        else os.environ.get("ADMIN_TOKEN")
    )
    if not expected:
        raise HTTPException(
            401,
            "Admin routes are locked because ADMIN_TOKEN is not set on the server.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Invalid or missing X-Admin-Token")
    return True
