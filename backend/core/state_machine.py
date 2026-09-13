from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.database import clog, db, from_mongo, now, now_iso, to_mongo
from core.models import Event, Lead, LeadStatus

STATUSES: list[str] = [
    "NEW",
    "CALLING",
    "IN_CONVERSATION",
    "QUALIFIED",
    "NURTURE",
    "HOT",
    "BOOKED",
]

ACTIVE: set[str] = {"NEW", "CALLING", "IN_CONVERSATION"}
TERMINAL: set[str] = {"QUALIFIED", "HOT", "NURTURE", "BOOKED"}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"CALLING", "NURTURE"},
    "CALLING": {"IN_CONVERSATION", "NURTURE", "NEW"},
    "IN_CONVERSATION": {"QUALIFIED", "NURTURE", "HOT"},
    "QUALIFIED": {"BOOKED", "NURTURE"},
    "HOT": {"BOOKED", "QUALIFIED", "NURTURE"},
    "NURTURE": {"CALLING", "QUALIFIED", "HOT"},
    "BOOKED": {"NURTURE"},
}


def is_legal(current: str, target: str) -> bool:
    return target == current or target in ALLOWED_TRANSITIONS.get(current, set())


def can_transition(from_s: str, to_s: str) -> bool:
    return is_legal(from_s, to_s)


async def record_event(
    lead_id: str,
    kind: str,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str = "",
    meta: dict[str, Any] | None = None,
) -> None:
    ev = Event(
        lead_id=lead_id,
        kind=kind,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        meta=meta or {},
    )
    await db.events.insert_one(to_mongo(ev))


async def transition(lead_id: str, new_status: str, reason: str = "") -> Lead:
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")
    lead = from_mongo(Lead, lead_doc)
    if new_status == lead.status:
        return lead
    if not is_legal(lead.status, new_status):
        raise HTTPException(400, f"Illegal transition {lead.status} -> {new_status}")
    old = lead.status
    lead.status = new_status  # type: ignore[assignment]
    lead.updated_at = now()
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"status": new_status, "updated_at": lead.updated_at.isoformat()}},
    )
    await record_event(lead_id, "transition", old, new_status, reason)
    clog(lead_id).info("transition %s -> %s (%s)", old, new_status, reason)
    return lead


async def touch(lead_id: str, **fields: Any) -> None:
    """Update lead fields and bump ``updated_at`` (which /tick uses for timeouts)."""
    fields["updated_at"] = now_iso()
    await db.leads.update_one({"id": lead_id}, {"$set": fields})
