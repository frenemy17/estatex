from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

import providers
from core.database import db, from_mongo, to_mongo
from core.models import (
    Appointment,
    BookSlotRequest,
    Event,
    Lead,
    LeadCreate,
    ScheduledAction,
)
from core.pipeline import run_ai_pipeline, run_supervisor
from core.rate_limit import rate_limit
from core.services import fetch_slots, record_provider
from core.state_machine import is_legal, record_event, touch, transition
from routes.auth import require_admin

router = APIRouter(tags=["leads"])


async def _ingest_lead(
    name: str,
    phone: str,
    email: str | None,
    source: str,
    bg: BackgroundTasks,
    extra_meta: dict | None = None,
) -> Lead:
    """Shared ingestion: dedupe by phone, insert, dispatch the AI pipeline."""
    existing = await db.leads.find_one({"phone": phone})
    if existing:
        return from_mongo(Lead, existing)
    lead = Lead(name=name, phone=phone, email=email, source=source)
    await db.leads.insert_one(to_mongo(lead))
    await record_event(
        lead.id, "note", reason="lead.captured", meta={"source": source, **(extra_meta or {})}
    )
    bg.add_task(run_ai_pipeline, lead.id)
    return lead


@router.post("/lead", response_model=Lead)
async def create_lead(payload: LeadCreate, bg: BackgroundTasks, request: Request):
    await rate_limit(request, "lead")
    return await _ingest_lead(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        source=payload.source,
        bg=bg,
    )


@router.post("/leads/bulk", dependencies=[Depends(require_admin)])
async def bulk_create_leads(payload: list[LeadCreate], bg: BackgroundTasks):
    results = []
    for p in payload:
        results.append(
            await _ingest_lead(
                name=p.name,
                phone=p.phone,
                email=p.email,
                source=p.source or "csv_import",
                bg=bg,
            )
        )
    return {"imported": len(results), "leads": results}


@router.get("/leads", response_model=list[Lead])
async def list_leads():
    docs = await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [from_mongo(Lead, d) for d in docs]


@router.get("/leads/{lead_id}", response_model=Lead)
async def get_lead(lead_id: str):
    doc = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lead not found")
    return from_mongo(Lead, doc)


@router.get("/leads/{lead_id}/events", response_model=list[Event])
async def get_events(lead_id: str):
    docs = await db.events.find({"lead_id": lead_id}, {"_id": 0}).sort("ts", 1).to_list(500)
    return [from_mongo(Event, d) for d in docs]


@router.get("/leads/{lead_id}/appointments", response_model=list[Appointment])
async def get_appointments(lead_id: str):
    docs = await db.appointments.find({"lead_id": lead_id}, {"_id": 0}).to_list(50)
    return [from_mongo(Appointment, d) for d in docs]


@router.get("/leads/{lead_id}/scheduled", response_model=list[ScheduledAction])
async def get_scheduled(lead_id: str):
    docs = (
        await db.scheduled_actions.find({"lead_id": lead_id}, {"_id": 0})
        .sort("run_at", 1)
        .to_list(50)
    )
    return [from_mongo(ScheduledAction, d) for d in docs]


@router.get("/leads/{lead_id}/slots")
async def get_slots(lead_id: str):
    return await fetch_slots(lead_id)


@router.get("/leads/{lead_id}/checkpoint")
async def get_checkpoint(lead_id: str):
    doc = await db.graph_checkpoints.find_one({"_id": lead_id})
    if not doc:
        return {"state": None, "current_node": None}
    return {"state": doc.get("state"), "current_node": doc.get("current_node")}


@router.post("/leads/{lead_id}/book", response_model=Appointment)
async def book(lead_id: str, req: BookSlotRequest):
    """Reserve a viewing."""
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    if not is_legal(doc["status"], "BOOKED"):
        raise HTTPException(400, f"Illegal transition {doc['status']} -> BOOKED")

    result = await providers.booker.book(
        slot_iso=req.slot_iso, name=doc.get("name", "Lead"), email=doc.get("email")
    )
    if not result.ok:
        await record_provider(result, lead_id, reason="booking.failed", kind="error")
        raise HTTPException(
            502,
            f"Booking rejected by Cal.com (HTTP {result.status}): {result.error}",
        )
    await record_provider(result, lead_id=None)

    appt = Appointment(
        lead_id=lead_id,
        slot_iso=req.slot_iso,
        provider=result.provider,
        external_id=result.data.get("booking_id"),
    )
    await db.appointments.insert_one(to_mongo(appt))
    await transition(lead_id, "BOOKED", "booking.confirmed")
    await record_event(
        lead_id,
        "booking",
        reason="booking.created",
        meta={
            "slot": req.slot_iso,
            "appointment_id": appt.id,
            "external_id": appt.external_id,
            **result.to_meta(),
        },
    )
    return appt


@router.post("/leads/{lead_id}/supervisor")
async def supervisor(lead_id: str):
    return await run_supervisor(lead_id)


@router.post("/leads/{lead_id}/rerun")
async def rerun(lead_id: str, bg: BackgroundTasks):
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    await record_event(
        lead_id, "note", from_status=doc["status"], reason="pipeline.reset"
    )
    await transition(lead_id, "NURTURE", "pipeline.reset")
    await touch(
        lead_id,
        score=0,
        qualification=None,
        transcript=[],
        awaiting_transcript=False,
        voice_call_id=None,
    )
    bg.add_task(run_ai_pipeline, lead_id)
    return {"ok": True}


@router.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=True)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    return result


@router.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: str):
    result = await run_supervisor(lead_id, approve=False)
    await db.leads.update_one({"id": lead_id}, {"$set": {"pending_approval": False}})
    lead_doc = await db.leads.find_one({"id": lead_id})
    if lead_doc and lead_doc["status"] == "HOT":
        try:
            await transition(lead_id, "NURTURE", reason="escalation.rejected")
        except HTTPException:
            pass
    return result


@router.post("/leads/{lead_id}/opt-out")
async def opt_out(lead_id: str):
    result = await db.leads.update_one({"id": lead_id}, {"$set": {"opted_out": True}})
    if not result.matched_count:
        raise HTTPException(404, "Lead not found")
    await record_event(lead_id, "note", reason="lead.opted_out")
    return {"ok": True}
