from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta

from fastapi import HTTPException

import providers
from core.database import clog, db, from_mongo, log, now, now_iso
from core.models import Lead
from core.scoring import qualify_and_route
from core.services import (
    CALL_TIMEOUT_MINUTES,
    SUPERVISOR_WAIT_HOURS,
    record_provider,
    send_notification,
)
from core.state_machine import (
    ALLOWED_TRANSITIONS,
    is_legal,
    record_event,
    touch,
    transition,
)

_background_tasks: set[asyncio.Task] = set()


def _dispatch_pipeline_sync(lead_id: str) -> None:
    """Fire-and-forget pipeline dispatch used by the graph's 'call' node."""
    task = asyncio.create_task(run_ai_pipeline(lead_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _schedule_supervisor_check(lead_id: str, hours: int | None = None) -> str:
    """Backs the supervisor's ``wait`` node with a real queued action."""
    from core.tick import schedule_action

    run_at = now() + timedelta(hours=hours if hours is not None else SUPERVISOR_WAIT_HOURS)
    await schedule_action(lead_id, "supervisor", run_at, reason="supervisor.wait")
    await touch(lead_id, next_check_at=run_at.isoformat())
    return run_at.isoformat()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    srv = sys.modules.get("server")
    if srv is not None and getattr(srv, "_compiled_graph", None) is not None:
        return srv._compiled_graph

    if _compiled_graph is None:
        from agents.supervisor import build_supervisor_graph  # local import

        _compiled_graph = build_supervisor_graph(
            db,
            send_notification,
            _dispatch_pipeline_sync,
            _schedule_supervisor_check,
        )
        if srv is not None:
            srv._compiled_graph = _compiled_graph
    return _compiled_graph


async def run_supervisor(lead_id: str, approve: bool | None = None) -> dict:
    """Invoke the compiled graph. If approve is set, resume from the interrupt."""
    lead_doc = await db.leads.find_one({"id": lead_id})
    if not lead_doc:
        raise HTTPException(404, "Lead not found")

    graph = get_graph()
    initial: dict = {"lead_id": lead_id}
    if approve is not None:
        initial["approved"] = approve
        state = await graph.ainvoke(initial, thread_id=lead_id, resume=True)
    else:
        state = await graph.ainvoke(initial, thread_id=lead_id)

    existing = lead_doc.get("supervisor_trace") or []
    merged_trace = existing + [s for s in state.get("trace", []) if s not in existing]
    await db.leads.update_one(
        {"id": lead_id},
        {
            "$set": {
                "supervisor_trace": merged_trace,
                "pending_approval": bool(
                    state.get("requires_approval") and state.get("_interrupt_at")
                ),
                "updated_at": now_iso(),
            }
        },
    )
    await record_event(
        lead_id,
        "supervisor",
        reason=f"next_action={state.get('next_action')}",
        meta={
            "trace_len": len(state.get("trace", [])),
            "requires_approval": bool(state.get("requires_approval")),
            "interrupt_at": state.get("_interrupt_at"),
            "approved": state.get("approved"),
        },
    )
    return {
        "next_action": state.get("next_action"),
        "trace": state.get("trace", []),
        "requires_approval": bool(
            state.get("requires_approval") and state.get("_interrupt_at")
        ),
        "decision": state.get("decision"),
        "enrichment": state.get("enrichment"),
        "followup_plan": state.get("followup_plan"),
    }


async def _move_to_calling(lead: Lead) -> bool:
    """Try to put a lead into CALLING, honouring the state machine."""
    if lead.status == "CALLING":
        return True
    if is_legal(lead.status, "CALLING"):
        await transition(lead.id, "CALLING", "ai.dispatch")
        return True
    await record_event(
        lead.id,
        "error",
        from_status=lead.status,
        reason="call.blocked",
        meta={
            "detail": f"cannot dial from {lead.status}",
            "legal_next": sorted(ALLOWED_TRANSITIONS.get(lead.status, set())),
        },
    )
    clog(lead.id).info("call blocked from status=%s", lead.status)
    return False


async def run_ai_pipeline(lead_id: str) -> None:
    """Dial the lead, then qualify."""
    from core.tick import schedule_action

    try:
        lead_doc = await db.leads.find_one({"id": lead_id})
        if not lead_doc:
            log.warning("pipeline: lead %s not found", lead_id)
            return
        lead = from_mongo(Lead, lead_doc)

        if not await _move_to_calling(lead):
            return

        delay = float(os.environ.get("DEMO_CALL_DELAY_SECONDS", "1.2" if providers.demo_mode() else "0"))
        if delay > 0:
            await asyncio.sleep(delay)  # visual beat for the demo only

        call = await providers.voice.start_call(
            lead_id=lead.id, name=lead.name, phone=lead.phone, profile=lead.sim_profile
        )

        if call.live_failure:
            await record_provider(call, lead_id, reason="call.failed", kind="error")
            await transition(lead_id, "NURTURE", "call.failed")
            await schedule_action(
                lead_id,
                "supervisor",
                now() + timedelta(hours=2),
                reason="retry_after_call_failure",
            )
            return

        await record_provider(call, lead_id=None)
        attempts = list(lead.attempt_history) + [
            {
                "kind": "call",
                "provider": call.provider,
                "mode": call.mode,
                "ts": now_iso(),
            }
        ]
        transcript = call.data.get("transcript")

        if not transcript:
            await touch(
                lead_id,
                attempt_history=attempts,
                voice_call_id=call.data.get("call_id"),
                awaiting_transcript=True,
            )
            await record_event(
                lead_id,
                "call",
                reason="call.awaiting_transcript",
                meta={
                    **call.to_meta(),
                    "call_id": call.data.get("call_id"),
                    "timeout_minutes": CALL_TIMEOUT_MINUTES,
                },
            )
            clog(lead_id).info("live call in flight, awaiting webhook transcript")
            return

        await touch(
            lead_id,
            transcript=transcript,
            attempt_history=attempts,
            awaiting_transcript=False,
        )
        await record_event(
            lead_id, "call", reason="call.completed", meta={"turns": len(transcript), **call.to_meta()}
        )
        await qualify_and_route(lead_id)
    except Exception as e:  # noqa: BLE001
        clog(lead_id).exception("ai pipeline failed: %s", e)
        await record_event(
            lead_id, "error", reason="pipeline.error", meta={"error": str(e)[:500]}
        )
