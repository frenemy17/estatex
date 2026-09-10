from __future__ import annotations

from routes.admin import router as admin_router
from routes.auth import require_admin
from routes.leads import router as leads_router
from routes.providers import router as providers_router
from routes.webhooks import router as webhooks_router

__all__ = [
    "admin_router",
    "leads_router",
    "providers_router",
    "require_admin",
    "webhooks_router",
]
