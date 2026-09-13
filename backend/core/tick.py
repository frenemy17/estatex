from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from core.database import clog, db, log, now, now_iso, to_mongo
from core.models import ScheduledAction
from core.pipeline import run_supervisor
from core.scoring import qualify_and_route
from core.services import CALL_TIMEOUT_MINUTES, send_notification
from core.state_machine import record_event, touch, transition

MAX_SCHEDULED_ATTEMPTS = int(os.environ.get("MAX_SCHEDULED_ATTEMPTS", "5"))
BACKOFF_BASE_SECONDS = int(os.environ.get("BACKOFF_BASE_SECONDS", "30"))
MAX_BACKOFF_SECONDS = int(os.environ.get("MAX_BACKOFF_SECONDS", "3600"))


def compute_backoff_seconds(attempt: int) -> int:
    """Calculate exponential backoff delay: base * 2^(attempt - 1), capped at max."""
    return min(BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)), MAX_BACKOFF_SECONDS)


async def schedule_action(
    lead_id: str,
    kind: str,
    run_at: datetime,
    payload: dict | None = None,
    reason: str = "",
) -> ScheduledAction:
    action = ScheduledAction(
        lead_id=lead_id,
        kind=kind,
        run_at=run_at.isoformat(),
        payload=payload or {},
        reason=reason,
    )
    await db.scheduled_actions.insert_one(to_mongo(action))
    clog(lead_id).info("scheduled %s at %s (%s)", kind, action.run_at, reason)
    return action


async def _run_scheduled(doc: dict) -> str:
    """Execute one due action. Returns a short label for the tick summary."""
    kind = doc.get("kind")
    lead_id = doc["lead_id"]
    payload = doc.get("payload") or {}

    if kind == "supervisor":
        await run_supervisor(lead_id)
        return "supervisor"

    if kind == "notify":
        lead_doc = await db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead_doc:
            return "notify:lead_missing"
        await send_notification(
            lead_doc,
            payload.get("channel", "email"),
            payload.get("template", "nurture_sequence"),
            payload.get("ctx"),
        )
        return "notify"

    raise ValueError(f"unknown scheduled action kind: {kind}")


async def run_tick(limit: int = 25) -> dict:
    """One idempotent autonomy pass. This is the whole scheduler.

    1. drain due ``scheduled_actions`` with exponential retries and dead-letter queue
    2. rescue leads stranded mid-call (a serverless freeze or a dropped webhook
       would otherwise leave them in CALLING forever)

    Safe to run concurrently: each action is claimed with a conditional update,
    so two overlapping ticks cannot run the same row twice.
    """
    started = now()
    summary: dict[str, Any] = {
        "ran_at": started.isoformat(),
        "drained": 0,
        "failed": 0,
        "retried": 0,
        "dead_lettered": 0,
        "rescued": 0,
        "requalified": 0,
        "actions": [],
    }

    due = (
        await db.scheduled_actions.find(
            {
                "state": {"$in": ["PENDING", "FAILED"]},
                "run_at": {"$lte": started.isoformat()},
            }
        )
        .sort("run_at", 1)
        .to_list(limit)
    )

    for doc in due:
        claim = await db.scheduled_actions.update_one(
            {"id": doc["id"], "state": {"$in": ["PENDING", "FAILED"]}},
            {"$set": {"state": "RUNNING", "started_at": now_iso()}, "$inc": {"attempts": 1}},
        )
        if not claim.modified_count:
            continue  # another tick claimed it
        try:
            label = await _run_scheduled(doc)
            await db.scheduled_actions.update_one(
                {"id": doc["id"]},
                {"$set": {"state": "DONE", "finished_at": now_iso(), "error": None}},
            )
            summary["drained"] += 1
            summary["actions"].append(
                {"lead_id": doc["lead_id"], "kind": doc.get("kind"), "result": label}
            )
        except Exception as e:  # noqa: BLE001
            clog(doc["lead_id"]).exception("scheduled action failed: %s", e)
            attempts = (doc.get("attempts") or 0) + 1
            max_att = doc.get("max_attempts") or MAX_SCHEDULED_ATTEMPTS
            err_str = str(e)[:500]

            if attempts < max_att:
                delay = compute_backoff_seconds(attempts)
                next_run = started + timedelta(seconds=delay)
                await db.scheduled_actions.update_one(
                    {"id": doc["id"]},
                    {
                        "$set": {
                            "state": "FAILED",
                            "run_at": next_run.isoformat(),
                            "error": str(e),
                            "last_error": err_str,
                            "failed_at": now_iso(),
                        }
                    },
                )
                await record_event(
                    doc["lead_id"],
                    "error",
                    reason=f"scheduled.{doc.get('kind')}_failed",
                    meta={
                        "error": err_str,
                        "action_id": doc["id"],
                        "attempt": attempts,
                        "max_attempts": max_att,
                        "next_run_at": next_run.isoformat(),
                        "retrying": True,
                    },
                )
                summary["retried"] += 1
            else:
                await db.scheduled_actions.update_one(
                    {"id": doc["id"]},
                    {
                        "$set": {
                            "state": "DEAD_LETTER",
                            "finished_at": now_iso(),
                            "error": str(e),
                            "last_error": err_str,
                            "failed_at": now_iso(),
                            "dead_letter_reason": f"Exceeded max attempts ({max_att})",
                        }
                    },
                )
                await record_event(
                    doc["lead_id"],
                    "error",
                    reason="scheduled.dead_letter",
                    meta={
                        "error": err_str,
                        "action_id": doc["id"],
                        "attempts": attempts,
                        "max_attempts": max_att,
                    },
                )
                summary["dead_lettered"] += 1
            summary["failed"] += 1

    cutoff = (started - timedelta(minutes=CALL_TIMEOUT_MINUTES)).isoformat()
    stuck = await db.leads.find(
        {"status": {"$in": ["CALLING", "IN_CONVERSATION"]}, "updated_at": {"$lt": cutoff}},
        {"_id": 0},
    ).to_list(50)

    for doc in stuck:
        lead_id = doc["id"]
        if doc.get("transcript"):
            # A transcript landed but qualification never ran (process died
            # mid-pipeline). Resume rather than discard the conversation.
            try:
                await qualify_and_route(lead_id)
                summary["requalified"] += 1
                summary["actions"].append({"lead_id": lead_id, "kind": "requalify"})
            except Exception as e:  # noqa: BLE001
                clog(lead_id).exception("tick requalify failed: %s", e)
                summary["failed"] += 1
            continue

        await record_event(
            lead_id,
            "error",
            reason="call.timeout",
            meta={
                "waited_minutes": CALL_TIMEOUT_MINUTES,
                "voice_call_id": doc.get("voice_call_id"),
                "detail": "no transcript received before timeout",
            },
        )
        try:
            await transition(lead_id, "NURTURE", "call.timeout")
            await touch(lead_id, awaiting_transcript=False)
            summary["rescued"] += 1
            summary["actions"].append({"lead_id": lead_id, "kind": "rescue"})
        except HTTPException as e:
            clog(lead_id).warning("tick rescue blocked: %s", e.detail)
            summary["failed"] += 1

    summary["took_ms"] = int((now() - started).total_seconds() * 1000)
    log.info(
        "tick drained=%s failed=%s rescued=%s requalified=%s",
        summary["drained"],
        summary["failed"],
        summary["rescued"],
        summary["requalified"],
    )
    return summary
