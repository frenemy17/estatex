from __future__ import annotations

from fastapi import APIRouter

import providers
from core.database import db

router = APIRouter(tags=["providers"])


@router.get("/providers")
async def list_providers():
    """Per-provider mode plus the outcome of its last real call.

    Drives the dashboard status chips: grey = MOCK, green = LIVE and healthy,
    amber = LIVE but failing (with the real status code).
    """
    docs = await db.provider_health.find({}).to_list(50)
    health = {d["_id"]: d for d in docs}
    out = []
    for spec in providers.all_provider_status():
        h = health.get(spec["name"], {})
        out.append(
            {
                **spec,
                "last_ok": h.get("ok"),
                "last_status": h.get("status"),
                "last_error": h.get("error"),
                "last_provider": h.get("provider"),
                "last_call_at": h.get("at"),
                "calls": h.get("calls", 0),
                "failures": h.get("failures", 0),
            }
        )
    return {"demo_mode": providers.demo_mode(), "providers": out}
